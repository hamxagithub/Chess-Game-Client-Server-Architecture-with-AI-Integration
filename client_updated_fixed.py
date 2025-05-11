import socket
import threading
import json
import tkinter as tk
from tkinter import messagebox, scrolledtext, simpledialog
import chess
from PIL import Image, ImageTk
import os
import time

SERVER_IP = '127.0.0.1'
PORT = 5555
ASSET_PATH = "assets"  # Corrected path to your assets directory

# Mapping of piece symbols to asset filenames
PIECE_MAP = {
    'P': 'p', 'R': 'r', 'N': 'n', 'B': 'b', 'Q': 'q', 'K': 'k'
}

# Debug flag for verbose logging
DEBUG = True


def debug_print(message):
    """Print debug messages if DEBUG is enabled"""
    if DEBUG:
        print(f"[CLIENT DEBUG] {message}")


class ChessClient:
    def __init__(self, root):
        self.root = root
        self.root.title("Multiplayer Chess")
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        self.board = chess.Board()
        self.my_color = None  # Will be set to "white" or "black"
        self.selected_square = None
        self.images = {}
        self.buttons = {}
        self.is_my_turn = False
        self.game_active = False
        self.connected = False

        # Timer related attributes
        self.move_timer_label = None
        self.remaining_time_seconds = 0
        self.timer_job_id = None

        # Create socket
        self.socket = None

        # Build the GUI first
        self.build_gui()

        # Show connection dialog
        self.show_connection_dialog()    
    def show_connection_dialog(self):
        """Show dialog for connection options"""
        dialog = tk.Toplevel(self.root)
        dialog.title("Connect to Chess Server")
        dialog.transient(self.root)
        dialog.grab_set()
        # Prevent closing with X button - must use connect or quit 
        dialog.protocol("WM_DELETE_WINDOW", lambda: self.on_connection_dialog_close(dialog))        # Fields for server details
        tk.Label(dialog, text="Server IP:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        ip_entry = tk.Entry(dialog)
        ip_entry.insert(0, SERVER_IP)
        ip_entry.grid(row=0, column=1, padx=5, pady=5)

        tk.Label(dialog, text="Port:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        port_entry = tk.Entry(dialog)
        port_entry.insert(0, str(PORT))
        port_entry.grid(row=1, column=1, padx=5, pady=5)
        
        # Let the Enter key trigger connection attempt
        def on_enter(event):
            on_connect()
            
        ip_entry.bind("<Return>", on_enter)
        port_entry.bind("<Return>", on_enter)        # Role selection
        role_var = tk.StringVar(value="player")
        player_radio = tk.Radiobutton(dialog, text="Join as Player (Multiplayer)", variable=role_var, value="player")
        player_radio.grid(row=2, column=0, columnspan=2, padx=5, pady=5)
        
        computer_radio = tk.Radiobutton(dialog, text="Play Against Computer", variable=role_var, value="computer")
        computer_radio.grid(row=3, column=0, columnspan=2, padx=5, pady=5)

        spectator_radio = tk.Radiobutton(dialog, text="Join as Spectator", variable=role_var, value="spectator")
        spectator_radio.grid(row=4, column=0, columnspan=2, padx=5, pady=5)

        # Computer difficulty frame (initially hidden)
        difficulty_frame = tk.Frame(dialog)
        difficulty_frame.grid(row=5, column=0, columnspan=2, padx=5, pady=5)
        tk.Label(difficulty_frame, text="Difficulty:").pack(side=tk.LEFT)
        difficulty_var = tk.StringVar(value="medium")
        easy_radio = tk.Radiobutton(difficulty_frame, text="Easy", variable=difficulty_var, value="easy")
        easy_radio.pack(side=tk.LEFT, padx=5)
        medium_radio = tk.Radiobutton(difficulty_frame, text="Medium", variable=difficulty_var, value="medium")
        medium_radio.pack(side=tk.LEFT, padx=5)
        hard_radio = tk.Radiobutton(difficulty_frame, text="Hard", variable=difficulty_var, value="hard")
        hard_radio.pack(side=tk.LEFT, padx=5)
        difficulty_frame.grid_remove()  # Hide initially

        game_id_frame = tk.Frame(dialog)
        game_id_frame.grid(row=6, column=0, columnspan=2, padx=5, pady=5)
        tk.Label(game_id_frame, text="Game ID:").pack(side=tk.LEFT)
        game_id_entry = tk.Entry(game_id_frame, state=tk.DISABLED)
        game_id_entry.pack(side=tk.LEFT, padx=5)        # Enable/disable game ID entry and difficulty options based on role
        def on_role_change(*args):
            selected_role = role_var.get()
            
            # Handle game ID field visibility
            if selected_role == "spectator":
                game_id_entry.config(state=tk.NORMAL)
                game_id_frame.grid()
            else:
                game_id_entry.config(state=tk.DISABLED)
                
            # Handle difficulty frame visibility
            if selected_role == "computer":
                difficulty_frame.grid()
            else:
                difficulty_frame.grid_remove()

        role_var.trace("w", on_role_change)        # Status label for connection feedback
        status_label = tk.Label(dialog, text="", font=("Arial", 10), fg="blue")
        status_label.grid(row=7, column=0, columnspan=2, pady=5)# Connection button
        def on_connect():
            status_label.config(text="Connecting...", fg="blue")
            dialog.update()  # Update the UI to show the status message
            
            role = role_var.get()
            
            # Special handling for computer play
            if role == "computer":
                # No need to connect to server for computer play
                difficulty = difficulty_var.get()
                dialog.destroy()
                self.start_computer_game(difficulty)
                return
            
            # For online play (player or spectator)
            server_ip = ip_entry.get().strip()
            try:
                server_port = int(port_entry.get().strip())
                game_id = game_id_entry.get().strip() if role == "spectator" else ""

                # Attempt to connect - don't destroy dialog yet
                connection_successful = self.connect_to_server(server_ip, server_port, role, game_id)
                
                if connection_successful:
                    dialog.destroy()  # Only destroy dialog if connection was successful
                else:
                    # Reset status label if connection failed
                    status_label.config(text="Connection failed. Please try again.", fg="red")
            except ValueError:
                messagebox.showerror("Invalid Port", "Port must be an integer")
                status_label.config(text="Invalid port number. Please enter a valid number.", fg="red")
                  # Buttons frame
        buttons_frame = tk.Frame(dialog)
        buttons_frame.grid(row=8, column=0, columnspan=2, pady=10)
        
        connect_btn = tk.Button(buttons_frame, text="Connect", command=on_connect, width=10)
        connect_btn.pack(side=tk.LEFT, padx=10)
        
        quit_btn = tk.Button(
            buttons_frame, 
            text="Quit", 
            command=lambda: self.on_connection_dialog_close(dialog), 
            width=10
        )
        quit_btn.pack(side=tk.RIGHT, padx=10)

        # Center the dialog
        dialog.update_idletasks()
        x = self.root.winfo_rootx() + (self.root.winfo_width() - dialog.winfo_width()) // 2
        y = self.root.winfo_rooty() + (self.root.winfo_height() - dialog.winfo_height()) // 2
        dialog.geometry(f"+{x}+{y}")    
    def connect_to_server(self, ip, port, role="player", game_id=""):
        """Connect to the chess server"""
        try:
            # Create a new socket if needed
            if hasattr(self, 'socket') and self.socket:
                try:
                    self.socket.close()
                except:
                    pass
                
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            
            # Set timeout for connection attempt
            self.socket.settimeout(5)
            debug_print(f"Attempting to connect to {ip}:{port}...")
            
            # Try to connect to the server
            try:
                self.socket.connect((ip, port))
            except ConnectionRefusedError:
                debug_print("Connection refused. Server might not be running.")
                messagebox.showerror("Connection Error", "Connection refused. Make sure the server is running.")
                self.socket.close()
                return False
            except socket.timeout:
                debug_print("Connection timed out")
                messagebox.showerror("Connection Error", "Connection timed out. Server might be unreachable.")
                self.socket.close()
                return False
                
            # Connection successful, remove timeout
            self.socket.settimeout(None)
            self.connected = True
            debug_print(f"Connected to server at {ip}:{port} as {role}")

            # Send join request based on role
            join_msg = {
                "type": "join",
                "role": role
            }

            if role == "spectator" and game_id:
                join_msg["game_id"] = game_id

            debug_print(f"Sending: {join_msg}")
            try:
                self.socket.send(json.dumps(join_msg).encode())
            except Exception as e:
                debug_print(f"Error sending join message: {e}")
                messagebox.showerror("Connection Error", f"Error sending join message: {str(e)}")
                self.socket.close()
                self.connected = False
                return False

            if role == "player":
                self.show_info("Connected! Waiting for a game...")
            else:  # spectator
                self.show_info(f"Connected as spectator for game #{game_id}...")

            # Start receiving thread
            threading.Thread(target=self.receive_data, daemon=True).start()
            return True
        
        except Exception as e:
            error_msg = f"Connection Error: {str(e)}"
            debug_print(error_msg)
            messagebox.showerror("Connection Error", f"{str(e)}\n\nPlease check the IP address and port number.")
            if hasattr(self, 'socket') and self.socket:
                try:
                    self.socket.close()
                except:
                    pass
            self.connected = False
            return False

    def build_gui(self):
        """Set up the GUI components"""
        # Main frames
        main_frame = tk.Frame(self.root)
        main_frame.pack(padx=10, pady=10)

        # Left side: chess board
        self.board_frame = tk.Frame(main_frame)
        self.board_frame.grid(row=0, column=0, padx=10)

        # Right side: chat and info
        right_frame = tk.Frame(main_frame)
        right_frame.grid(row=0, column=1, padx=10, sticky="ns")

        # Game info panel
        info_frame = tk.Frame(right_frame)
        info_frame.pack(fill=tk.X, pady=(0, 10))        # Add buttons frame
        buttons_frame = tk.Frame(info_frame)
        buttons_frame.pack(fill=tk.X, pady=5)
        
        # Add Lobby button
        lobby_button = tk.Button(buttons_frame, text="Lobby", command=self.show_lobby,
                                font=("Arial", 10), bg="#FF9800", fg="white", width=8)
        lobby_button.pack(side=tk.LEFT, padx=5)
        
        # Add Quit Game button
        self.quit_button = tk.Button(buttons_frame, text="Quit Game", command=self.quit_current_game,
                               font=("Arial", 10), bg="#F44336", fg="white", width=8, state=tk.DISABLED)
        self.quit_button.pack(side=tk.RIGHT, padx=5)

        self.status_label = tk.Label(info_frame, text="Waiting for connection...", font=("Arial", 12))
        self.status_label.pack(pady=5)

        self.turn_label = tk.Label(info_frame, text="", font=("Arial", 10))
        self.turn_label.pack(pady=2)

        # Add move timer label
        self.move_timer_label = tk.Label(info_frame, text="", font=("Arial", 10, "bold"), fg="blue")
        self.move_timer_label.pack(pady=2)

        # Chat area
        chat_frame = tk.Frame(right_frame)
        chat_frame.pack(fill=tk.BOTH, expand=True)

        tk.Label(chat_frame, text="Chat", font=("Arial", 10, "bold")).pack(anchor="w")

        self.chat_area = scrolledtext.ScrolledText(chat_frame, state='disabled', width=30, height=15, wrap=tk.WORD)
        self.chat_area.pack(fill=tk.BOTH, expand=True, pady=5)

        # Chat input
        chat_input_frame = tk.Frame(right_frame)
        chat_input_frame.pack(fill=tk.X, pady=5)

        self.chat_entry = tk.Entry(chat_input_frame)
        self.chat_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.chat_entry.bind("<Return>", self.send_chat)

        send_btn = tk.Button(chat_input_frame, text="Send", command=self.send_chat)
        send_btn.pack(side=tk.RIGHT, padx=5)

        # Load chess piece images
        self.load_images()

        # Draw the initial board
        self.draw_board()

    def load_images(self):
        """Load chess piece images from assets directory"""
        for color in ['w', 'b']:
            for name in PIECE_MAP.values():
                img_key = f"{color}{name}"
                try:
                    path = os.path.join(ASSET_PATH, f"{color}_{name}.png")
                    if os.path.exists(path):
                        img = Image.open(path).resize((60, 60))
                        self.images[img_key] = ImageTk.PhotoImage(img)
                    else:
                        debug_print(f"Warning: Image file not found: {path}")
                except Exception as e:
                    debug_print(f"Error loading image {img_key}: {e}")   
    def draw_board(self):
        """Draw the chess board with current piece positions"""
        # Clear previous buttons
        for widget in self.board_frame.winfo_children():
            widget.destroy()

        self.buttons = {}

        # Draw new board
        for row in range(8):
            for col in range(8):
                square_idx = chess.square(col, 7 - row)  # Convert to chess library coordinates
                square_name = chess.square_name(square_idx)
                piece = self.board.piece_at(square_idx)

                # Determine square color
                color = "#f0d9b5" if (row + col) % 2 == 0 else "#b58863"

                # Highlight selected square
                if square_name == self.selected_square:
                    color = "#aaffaa"  # Light green for selected square
                    
                # Highlight last move (for computer games)
                elif hasattr(self, 'computer_ai') and self.board.move_stack:
                    last_move = self.board.peek()
                    if square_name == chess.square_name(last_move.from_square) or square_name == chess.square_name(last_move.to_square):
                        color = "#fff2a8"  # Light yellow for last move

                # Create button for the square
                btn = tk.Button(
                    self.board_frame,
                    bg=color,
                    width=4,
                    height=2,
                    command=lambda sq=square_name: self.on_square_click(sq)
                )

                # Update button state based on game state and turn
                btn_state = 'normal' if (self.game_active and self.is_my_turn) else 'disabled'
                btn.config(state=btn_state)
                debug_print(f"Square {square_name} button state: {btn_state}")

                btn.grid(row=row, column=col, sticky="nsew")

                # Add chess piece image if there's a piece on this square
                if piece:
                    prefix = 'w' if piece.color == chess.WHITE else 'b'
                    symbol = PIECE_MAP[piece.symbol().upper()]
                    img = self.images.get(prefix + symbol)
                    if img:
                        btn.config(image=img, width=60, height=60)

                # Store button reference
                self.buttons[square_name] = btn
                
        # Force update the UI to show changes immediately
        self.root.update()

    def on_square_click(self, square):
        """Handle chess square click"""
        debug_print(
            f"Square clicked: {square} (game_active={self.game_active}, is_my_turn={self.is_my_turn}, my_color={self.my_color})")

        if not self.game_active or not self.is_my_turn or self.my_color is None:
            debug_print("Cannot make move now")
            return

        # First click - select a piece to move
        if not self.selected_square:
            piece = self.board.piece_at(chess.parse_square(square))
            is_my_piece = False

            if piece:
                # Verify this is the player's piece
                is_my_piece = (
                        (piece.color == chess.WHITE and self.my_color == "white") or
                        (piece.color == chess.BLACK and self.my_color == "black")
                )
                debug_print(f"Selected piece: {piece}, is_my_piece: {is_my_piece}")

            if is_my_piece:
                self.selected_square = square
                self.draw_board()  # Redraw to highlight selected square

        # Second click - attempt to move the selected piece
        else:
            if square == self.selected_square:
                # Deselect if clicking the same square
                self.selected_square = None
                self.draw_board()
                return           
            try:
                # Create move from the selected squares
                move = chess.Move.from_uci(self.selected_square + square)
                debug_print(f"Attempting move: {move}")

                # Check if promotion is needed
                from_square = chess.parse_square(self.selected_square)
                piece = self.board.piece_at(from_square)
                is_pawn = piece and piece.piece_type == chess.PAWN
                is_promotion_rank = (
                        (self.my_color == "white" and square[1] == '8') or
                        (self.my_color == "black" and square[1] == '1')
                )

                # Handle pawn promotion
                if is_pawn and is_promotion_rank:
                    # Ask for promotion piece
                    promotion_options = {
                        "Queen": chess.QUEEN,
                        "Rook": chess.ROOK,
                        "Bishop": chess.BISHOP,
                        "Knight": chess.KNIGHT
                    }
                    promotion = simpledialog.askstring(
                        "Promotion",
                        "Promote to:",
                        parent=self.root
                    )

                    if promotion in promotion_options:
                        move.promotion = promotion_options[promotion]
                    else:
                        # Default to queen if canceled or invalid
                        move.promotion = chess.QUEEN
                        
                # Check if move is legal locally
                is_legal_locally = move in self.board.legal_moves

                # Handle move differently based on whether we're playing the computer or online
                if hasattr(self, 'computer_ai'):
                    # Computer play mode
                    if is_legal_locally:
                        debug_print(f"Move {move} is legal in computer mode")
                        
                        # Apply move locally
                        self.board.push(move)
                        self.is_my_turn = False  # Switch to computer's turn
                        self.draw_board()
                        
                        # Clear selection
                        self.selected_square = None
                        
                        # Update UI with move info
                        self.show_info("Computer is thinking...")
                        self.add_chat_message(f"Your move: {move}")
                        self.update_turn_label()
                        
                        # Check for game over conditions
                        if self.board.is_checkmate():
                            self.game_active = False
                            self.show_info("Checkmate! You won!")
                            self.add_chat_message("Game over: Checkmate! You win.")
                            self.quit_button.config(state=tk.DISABLED)
                            return
                            
                        elif self.board.is_stalemate():
                            self.game_active = False
                            self.show_info("Game drawn by stalemate!")
                            self.add_chat_message("Game over: Draw by stalemate.")
                            self.quit_button.config(state=tk.DISABLED)
                            return
                            
                        elif self.board.is_insufficient_material():
                            self.game_active = False
                            self.show_info("Game drawn - insufficient material!")
                            self.add_chat_message("Game over: Draw by insufficient material.")
                            self.quit_button.config(state=tk.DISABLED)
                            return
                        
                        # If game continues, have the computer make its move
                        self.computer_make_move()
                    else:
                        self.show_info("Illegal move!")
                        self.selected_square = None
                        self.draw_board()
                    
                else:
                    # Online play mode
                    if is_legal_locally:
                        debug_print(f"Move {move} is legal, sending to server")
                        # Send move to server
                        move_msg = {
                            "type": "move",
                            "move": move.uci()
                        }
                        debug_print(f"Sending: {move_msg}")
                        self.socket.send(json.dumps(move_msg).encode())

                        # Clear selection
                        self.selected_square = None

                        # Apply move locally (server will confirm with update)
                        self.board.push(move)
                        self.is_my_turn = False  # Temporarily disable until server confirms
                        self.draw_board()
                    else:
                        # Special case: There might be a sync issue, ask the server if the move is legal
                        debug_print(f"Move {move} appears illegal locally, but sending to server anyway to verify")
                        self.show_info("Checking move with server...")

                        move_msg = {
                            "type": "move",
                            "move": move.uci(),
                            "verify_only": True  # Ask server to verify if this move is valid
                        }
                        self.socket.send(json.dumps(move_msg).encode())

                        # Clear selection for now
                        self.selected_square = None
                        self.draw_board()
            except Exception as e:
                debug_print(f"Error processing move: {e}")
                self.show_info(f"Error: {str(e)}")
                self.selected_square = None
                self.draw_board()

    def send_chat(self, event=None):
        """Send chat message to server"""
        if not self.connected:
            return

        msg = self.chat_entry.get().strip()
        if msg:
            try:
                chat_msg = {
                    "type": "chat",
                    "msg": msg
                }
                debug_print(f"Sending chat: {chat_msg}")
                self.socket.send(json.dumps(chat_msg).encode())
                self.chat_entry.delete(0, tk.END)
            except Exception as e:
                debug_print(f"Error sending chat: {e}")
                self.show_info(f"Error sending chat: {str(e)}")

    def receive_data(self):
        """Handle data received from server"""
        buffer = ""

        while self.connected:            
            try:
                data = self.socket.recv(2048).decode()
                if not data:
                    debug_print("Empty data received from server, connection likely closed")
                    break

                debug_print(f"Received from server: {data}")
                buffer += data

                # Process complete JSON messages - handle multiple messages that may have arrived at once
                while buffer:
                    try:
                        # Try to find a complete JSON object
                        msg_end = 0
                        json_depth = 0
                        in_string = False
                        escape_next = False

                        for i, char in enumerate(buffer):
                            if escape_next:
                                escape_next = False
                                continue

                            if char == '\\':
                                escape_next = True
                            elif char == '"' and not escape_next:
                                in_string = not in_string
                            elif not in_string:
                                if char == '{':
                                    json_depth += 1
                                elif char == '}':
                                    json_depth -= 1
                                    if json_depth == 0:
                                        msg_end = i + 1
                                        break

                        if msg_end == 0:
                            # Incomplete JSON, wait for more data
                            break

                        # Process the complete message
                        msg_str = buffer[:msg_end]
                        buffer = buffer[msg_end:].strip()                       
                        msg = json.loads(msg_str)
                        # Process the message in the main UI thread
                        self.root.after(0, lambda m=msg: self.process_message(m))
                    
                    except json.JSONDecodeError as e:
                        debug_print(f"JSON decode error: {e}")
                        # Try to recover by discarding part of the buffer
                        if len(buffer) > 1000:  # If buffer is very large, just reset it
                            debug_print("Buffer too large, resetting")
                            buffer = ""
                        break
            except Exception as e:
                debug_print(f"Error receiving data: {e}")
                self.connected = False
                self.game_active = False  # Reset game state on connection loss
                self.my_color = None
                self.selected_square = None
                self.is_my_turn = False
                self.board = chess.Board()  # Reset board
                
                # Update UI with connection loss
                self.root.after(0, lambda: self.show_info("Connection to server lost"))
                
                # Enable reconnect option
                self.root.after(1000, self.show_connection_dialog)
                break

        debug_print("Receiver thread terminated")

    def process_message(self, msg):
        """Process message received from server"""
        try:
            msg_type = msg.get("type", "")
            debug_print(f"Processing message type: {msg_type}")

            if msg_type == "welcome":
                # Server welcome message
                self.show_info(f"Connected! {msg.get('message', '')}")

            elif msg_type == "info":
                # Server info message
                info_msg = msg.get("msg", "")
                self.show_info(info_msg)

                # Check if message contains "Joined lobby" to show the lobby UI
                if "Joined lobby" in info_msg:
                    self.root.after(100, self.show_lobby)
                  # Check if this is a game start info message
                if "Game #" in info_msg and "You are " in info_msg:
                    # Parse color from the message
                    if "You are White" in info_msg:
                        self.my_color = "white"
                        self.is_my_turn = True  # White goes first
                    elif "You are Black" in info_msg:
                        self.my_color = "black"
                        self.is_my_turn = False  # Black waits for white
                    self.game_active = True
                    self.update_turn_label()
                    self.draw_board()
                    # Enable the quit button when a game starts
                    self.quit_button.config(state=tk.NORMAL)
                    debug_print(f"Game started! Color: {self.my_color}, Turn: {self.is_my_turn}")
            
            elif msg_type == "lobby_update":
                # Lobby data update from server
                debug_print(f"Received lobby update: {msg}")
                # Call update_lobby with the correct data structure
                self.update_lobby(msg)

            elif msg_type == "game_start":
                # Explicit game start message (if implemented in the future)
                self.my_color = msg.get("color")
                self.game_active = True
                self.is_my_turn = self.my_color == "white"  # White goes first

                opponent = msg.get("opponent", "Anonymous")
                game_id = msg.get("game_id", "Unknown")

                self.show_info(f"Game #{game_id} started! You are playing as {self.my_color} against {opponent}")
                self.update_turn_label()
                self.draw_board()

            elif msg_type == "spectate_start":
                # Spectating a game
                game_id = msg.get("game_id", "Unknown")
                white = msg.get("white_player", "Black Player")
                black = msg.get("black_player", "Black Player")

                self.show_info(f"Spectating Game #{game_id}: {white} (white) vs {black} (black)")
                self.game_active = True  # For displaying the board

            elif msg_type == "board_update" or msg_type == "board":
                # Board state update
                fen = msg.get("fen") or msg.get("board")  # Try both field names
                if fen:
                    debug_print(f"Updating board with FEN: {fen}")
                    self.board = chess.Board(fen)

                # Update turn info based on the board state
                active_color = "white" if self.board.turn == chess.WHITE else "black"
                self.is_my_turn = (active_color == self.my_color)
                debug_print(
                    f"Board update: active_color={active_color}, my_color={self.my_color}, is_my_turn={self.is_my_turn}")

                # Redraw board with updated state
                self.draw_board()
                self.update_turn_label()

                # Check game status
                if msg.get("check", False):
                    self.show_info("Check!")

                if msg.get("game_over", False):
                    result = msg.get("result", "Unknown")
                    self.show_info(f"Game over! Result: {result}")
                    self.game_active = False

            elif msg_type == "timeout_sync":
                # Special handler for timeout synchronization
                fen = msg.get("board")
                next_turn = msg.get("next_turn", "").lower()
                timeout_player = msg.get("timeout_player")

                debug_print(f"Received timeout_sync: {timeout_player} timed out, next turn: {next_turn}, FEN: {fen}")

                # First fully reset our board with the server's state
                if fen:
                    self.board = chess.Board(fen)
                    debug_print(f"Reset board to server state: {fen}")

                # Update turn information
                if next_turn:
                    self.is_my_turn = (next_turn == self.my_color)
                    debug_print(f"After timeout, is_my_turn: {self.is_my_turn}")

                    if self.is_my_turn:
                        self.show_info(f"{timeout_player} player's turn expired. It's your turn now.")
                    else:
                        self.show_info(f"{timeout_player} player's turn expired. Waiting for opponent.")

                # Ensure the game is active after timeout synchronization
                self.game_active = True

                # Additional debug logs to verify state
                debug_print(f"Game active: {self.game_active}, Is my turn: {self.is_my_turn}")

                # Force redraw the board and update UI elements
                self.draw_board()
                self.update_turn_label()

                # Notify the player explicitly if it's their turn
                if self.is_my_turn:
                    self.show_info("It's your turn. Make a move!")

            elif msg_type == "move":
                # Move message from server
                move_uci = msg.get("move")
                board_fen = msg.get("board")

                debug_print(f"Move message received: move={move_uci}, board_fen={board_fen}")

                # Update the board based on the message
                if board_fen:
                    # Update board with provided FEN
                    self.board = chess.Board(board_fen)
                elif move_uci:
                    # Apply move if no board state provided
                    try:
                        move = chess.Move.from_uci(move_uci)
                        if move in self.board.legal_moves:
                            self.board.push(move)
                            debug_print(f"Applied move {move} locally")
                        else:
                            debug_print(f"Move {move} not in legal moves: {[m.uci() for m in self.board.legal_moves]}")
                    except Exception as e:
                        debug_print(f"Error applying move: {e}")

                # Update turn info after move
                active_color = "white" if self.board.turn == chess.WHITE else "black"
                self.is_my_turn = (active_color == self.my_color)
                debug_print(
                    f"After move: active_color={active_color}, my_color={self.my_color}, is_my_turn={self.is_my_turn}")
                # Redraw board and update turn indicator
                self.draw_board()
                self.update_turn_label()

            elif msg_type == "turn":
                # Turn update
                active_turn = msg.get("turn", "").lower()
                time_limit = msg.get("time_limit")
                debug_print(f"Turn message received: {active_turn}, time_limit: {time_limit}")

                if active_turn:
                    self.is_my_turn = (active_turn == self.my_color)
                    debug_print(
                        f"Turn update: active_turn={active_turn}, my_color={self.my_color}, is_my_turn={self.is_my_turn}")                    # Make sure to update the board state after turn changes
                    self.update_turn_label()                    # Stop any existing timer
                    self.stop_timer_countdown()
                    # Handle timer for move time limit
                    if self.game_active:
                        if self.is_my_turn and time_limit is not None:
                            self.remaining_time_seconds = int(time_limit)
                            self.start_timer_countdown()
                            # Force redraw board with pieces enabled when it becomes your turn
                            debug_print(f"It's now my turn, enabling board interaction")
                        elif not self.is_my_turn and time_limit is not None:
                            self.move_timer_label.config(text=f"Opponent's move ({time_limit}s)", fg="black")
                        else:
                            self.move_timer_label.config(text="")
                    # Always redraw the board when turn message is received to update button states
                    self.draw_board()
                    
            elif msg_type == "game_over":
                # Explicit game over message
                result = msg.get("result", "Game Over")
                reason = msg.get("reason", "")
                self.show_info(f"Game Over: {result}")
                
                # Reset game state
                self.game_active = False
                self.is_my_turn = False
                self.my_color = None  # Reset color assignment
                self.selected_square = None
                self.board = chess.Board()  # Reset to initial board position
                
                # Update UI
                self.quit_button.config(state=tk.DISABLED)  # Disable quit button when game ends
                self.stop_timer_countdown()
                if self.move_timer_label:
                    self.move_timer_label.config(text="Game Over", fg="red")
                self.draw_board()  # Redraw to disable all buttons
                
                # Clear the chat area when the game is over
                self.chat_area.configure(state='normal')
                self.chat_area.delete(1.0, tk.END)
                self.chat_area.configure(state='disabled')
                self.add_chat_message("Chat history cleared - Game ended")
                
                # Request to update the lobby display, in case we need to show available games
                self.request_lobby_update()
                
                # Show the lobby window after a short delay
                self.root.after(500, self.show_lobby)

            elif msg_type == "chat":
                # Chat message
                chat_msg = msg.get("msg", "")
                self.add_chat_message(chat_msg)

            elif msg_type == "error":
                # Error message
                error_msg = msg.get("msg") or msg.get("message", "Unknown error")
                self.show_info(f"Error: {error_msg}")

            else:
                debug_print(f"Unknown message type: {msg_type}")

        except Exception as e:
            debug_print(f"Error processing message: {e}")

    def add_chat_message(self, message):
        """Add a message to the chat area"""
        self.chat_area.configure(state='normal')
        self.chat_area.insert(tk.END, message + "\n")
        self.chat_area.see(tk.END)
        self.chat_area.configure(state='disabled')

    def show_info(self, message):
        """Display info message in status label and debug log"""
        debug_print(f"INFO: {message}")
        self.status_label.config(text=message)

    def update_turn_label(self):
        """Update the turn indicator label"""
        if not self.game_active:
            self.turn_label.config(text="")
            return

        if self.my_color:  # If player (not spectator)
            if self.is_my_turn:
                self.turn_label.config(text="Your turn", fg="green")
            else:
                self.turn_label.config(text="Opponent's turn", fg="red")
        else:  # Spectator
            active_color = "White" if self.board.turn == chess.WHITE else "Black"
            self.turn_label.config(text=f"{active_color}'s turn")

    def start_timer_countdown(self):
        """Start or update the move timer countdown"""
        # Cancel any existing timer job
        if hasattr(self, 'timer_job_id') and self.timer_job_id:
            self.root.after_cancel(self.timer_job_id)
            self.timer_job_id = None

        # Only continue if game is active, it's my turn, and there's time left
        if self.game_active and self.is_my_turn and self.remaining_time_seconds > 0:
            # Update the timer label with the current time
            self.move_timer_label.config(text=f"Your move: {self.remaining_time_seconds}s left", fg="red")
            # Decrement the timer
            self.remaining_time_seconds -= 1
            # Schedule the next update in 1 second
            self.timer_job_id = self.root.after(1000, self.start_timer_countdown)
        elif self.game_active and self.is_my_turn:
            # Time's up locally (server will enforce timeout)
            self.move_timer_label.config(text="Time's up! Waiting for server...", fg="orange")
        else:
            # Not my turn or game not active
            self.stop_timer_countdown()

    def stop_timer_countdown(self):
        """Stop the timer countdown and reset the timer label"""
        if hasattr(self, 'timer_job_id') and self.timer_job_id:
            self.root.after_cancel(self.timer_job_id)
            self.timer_job_id = None

        # Only reset the label if it's showing an active timer or waiting message
        if hasattr(self, 'move_timer_label') and self.move_timer_label:
            current_text = self.move_timer_label.cget("text")
            if ("Your move:" in current_text or
                    "Time's up!" in current_text or
                    current_text == "" or
                    "Waiting for game to start..." in current_text):
                self.move_timer_label.config(text="", fg="blue")

    def show_lobby(self):
        """Show the lobby UI"""
        # If a lobby window already exists, just focus on it instead of creating a new one
        if hasattr(self, 'lobby_window') and self.lobby_window.winfo_exists():
            self.lobby_window.focus_force()
            self.request_lobby_update()
            return
            
        lobby_window = tk.Toplevel(self.root)
        lobby_window.title("Chess Game Lobby")
        lobby_window.geometry("400x500")
        
        # Set transient property for better window management
        lobby_window.transient(self.root)

        # Title
        title_label = tk.Label(lobby_window, text="Chess Game Lobby", font=("Arial", 16, "bold"))
        title_label.pack(pady=10)

        # Players in the lobby
        tk.Label(lobby_window, text="Players in Lobby:", font=("Arial", 12, "bold")).pack(pady=5, anchor="w", padx=10)
        self.lobby_list = tk.Listbox(lobby_window, height=5, width=40)
        self.lobby_list.pack(pady=5, padx=10, fill=tk.X)

        # Available games
        tk.Label(lobby_window, text="Available Games:", font=("Arial", 12, "bold")).pack(pady=5, anchor="w", padx=10)
        self.available_games_list = tk.Listbox(lobby_window, height=10, width=40)
        self.available_games_list.pack(pady=5, padx=10, fill=tk.X)

        # Buttons frame
        button_frame = tk.Frame(lobby_window)
        button_frame.pack(pady=10, fill=tk.X)

        # Create game button
        create_button = tk.Button(button_frame, text="Create Game",
                                 font=("Arial", 11), width=15,
                                 command=self.create_game,
                                 bg="#4CAF50", fg="white")
        create_button.pack(side=tk.LEFT, padx=10)

        # Join game button
        join_button = tk.Button(button_frame, text="Join Game",
                               font=("Arial", 11), width=15,
                               command=self.join_selected_game,
                               bg="#2196F3", fg="white")
        join_button.pack(side=tk.RIGHT, padx=10)

        # Refresh button
        refresh_button = tk.Button(lobby_window, text="Refresh",
                                  font=("Arial", 10),
                                  command=self.request_lobby_update)
        refresh_button.pack(pady=10)

        # Status label
        self.lobby_status_label = tk.Label(lobby_window, text="", font=("Arial", 10))
        self.lobby_status_label.pack(pady=5)

        self.lobby_window = lobby_window

        # Set up automatic refresh timer (every 5 seconds)
        self.lobby_update_timer = lobby_window.after(5000, self.auto_refresh_lobby)
        
        # Set up protocol for window closing to cancel the timer
        lobby_window.protocol("WM_DELETE_WINDOW", self.on_lobby_window_close)
        
        # Request initial lobby data
        self.request_lobby_update()

    def auto_refresh_lobby(self):
        """Automatically refresh the lobby every few seconds"""
        if hasattr(self, 'lobby_window') and self.lobby_window.winfo_exists():
            self.request_lobby_update()
            # Schedule next update
            self.lobby_update_timer = self.lobby_window.after(5000, self.auto_refresh_lobby)
    
    def on_lobby_window_close(self):
        """Handle the closing of the lobby window"""
        # Cancel the update timer if it exists
        if hasattr(self, 'lobby_update_timer'):
            self.lobby_window.after_cancel(self.lobby_update_timer)
            
        # Destroy the window
        self.lobby_window.destroy()    
    def request_lobby_update(self):
        """Request the latest lobby state from the server"""
        if not self.connected:
            debug_print("Cannot request lobby update: not connected to server")
            if hasattr(self, 'lobby_status_label'):
                self.lobby_status_label.config(text="Not connected to server", fg="red")
            return False
            
        try:
            debug_print("Requesting lobby update from server")
            self.socket.send(json.dumps({"type": "lobby_request"}).encode())
            if hasattr(self, 'lobby_status_label'):
                self.lobby_status_label.config(text="Updating lobby data...", fg="blue")
            return True
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError) as e:
            debug_print(f"Connection error requesting lobby update: {e}")
            self.connected = False
            if hasattr(self, 'lobby_status_label'):
                self.lobby_status_label.config(text=f"Connection lost: {str(e)}", fg="red")
            # Schedule reconnection dialog
            self.root.after(1000, self.show_connection_dialog)
            return False
        except Exception as e:
            debug_print(f"Error requesting lobby update: {e}")
            if hasattr(self, 'lobby_status_label'):
                self.lobby_status_label.config(text=f"Error: {str(e)}", fg="red")
            return False

    def update_lobby(self, lobby_data):
        """Update the lobby UI with the latest state"""
        if not hasattr(self, 'lobby_window') or not self.lobby_window.winfo_exists():
            return

        debug_print(f"Updating lobby with data: {lobby_data}")
        players = lobby_data.get("players", [])
        available_games = lobby_data.get("available_games", [])
        
        # Update players list
        if hasattr(self, 'lobby_list'):
            self.lobby_list.delete(0, tk.END)
            if not players:
                self.lobby_list.insert(tk.END, "No players in lobby")
            else:
                for player in players:
                    self.lobby_list.insert(tk.END, f"Player: {player}")
          # Update available games list
        if hasattr(self, 'available_games_list'):
            self.available_games_list.delete(0, tk.END)
            if not available_games:
                self.available_games_list.insert(tk.END, "No available games")
            else:
                for game in available_games:
                    game_id = game.get("id", "Unknown")
                    creator = game.get("creator", "Unknown")
                    is_private = game.get("is_private", False)
                    
                    # Show a lock icon for private games
                    privacy_indicator = "🔒 " if is_private else ""
                    self.available_games_list.insert(tk.END, f"{privacy_indicator}Game #{game_id} - Created by {creator}")
        
        # Update status
        if hasattr(self, 'lobby_status_label'):
            self.lobby_status_label.config(text=f"Lobby updated: {len(players)} players, {len(available_games)} games")
            
    def create_game(self):
        """Send a request to create a new game"""
        if self.connected:
            try:
                # Ask if the user wants to create a private game
                use_password = messagebox.askyesno("Private Game", "Do you want to create a private game?")
                
                if use_password:
                    password = simpledialog.askstring("Game Password", 
                                                     "Enter a password for your game:", 
                                                     show='*')
                    self.socket.send(json.dumps({
                        "type": "create_game",
                        "password": password
                    }).encode())
                else:
                    self.socket.send(json.dumps({"type": "create_game"}).encode())
                    
                if hasattr(self, 'lobby_status_label'):
                    self.lobby_status_label.config(text="Creating game...")
                if hasattr(self, 'lobby_window'):
                    self.lobby_window.destroy()  # Close the lobby window
            except Exception as e:
                self.show_info(f"Error creating game: {e}")
                if hasattr(self, 'lobby_status_label'):
                    self.lobby_status_label.config(text=f"Error: {e}")
                    
    def join_selected_game(self):
        """Join the selected game from the list"""
        if not hasattr(self, 'available_games_list'):
            return

        selected = self.available_games_list.curselection()
        if not selected:
            if hasattr(self, 'lobby_status_label'):
                self.lobby_status_label.config(text="Please select a game to join")
            return

        game_text = self.available_games_list.get(selected[0])
        if "No available games" in game_text:
            return
        
        # Check if the game is private (has the lock icon)
        is_private = game_text.startswith("🔒")
            
        # Extract game ID - improved handling to avoid index errors
        try:
            # Extract game ID from text like "Game #12345 - Created by 127.0.0.1" or "🔒 Game #12345 - Created by 127.0.0.1"
            if "#" in game_text:
                parts = game_text.split("#")
                if len(parts) > 1:
                    game_id = parts[1].split(" ")[0]
                else:
                    if hasattr(self, 'lobby_status_label'):
                        self.lobby_status_label.config(text="Could not parse game ID")
                    return
            else:
                if hasattr(self, 'lobby_status_label'):
                    self.lobby_status_label.config(text="Invalid game format")
                return
        except Exception as e:
            debug_print(f"Error parsing game ID: {e}")
            if hasattr(self, 'lobby_status_label'):
                self.lobby_status_label.config(text=f"Error: {e}")
            return

        if self.connected:
            try:
                # If the game is private, ask for a password
                password = None
                if is_private:
                    password = simpledialog.askstring("Private Game", 
                                                    f"Enter password for game #{game_id}:", 
                                                    show='*')
                    if not password:  # User canceled
                        if hasattr(self, 'lobby_status_label'):
                            self.lobby_status_label.config(text="Join canceled")
                        return
                
                join_request = {
                    "type": "join_game",
                    "game_id": game_id
                }
                
                # Add password if provided
                if password:
                    join_request["password"] = password
                
                self.socket.send(json.dumps(join_request).encode())

                if hasattr(self, 'lobby_status_label'):
                    self.lobby_status_label.config(text=f"Joining game #{game_id}...")
                if hasattr(self, 'lobby_window'):
                    self.lobby_window.destroy()  # Close the lobby window

            except Exception as e:
                self.show_info(f"Error joining game: {e}")
                if hasattr(self, 'lobby_status_label'):
                    self.lobby_status_label.config(text=f"Error: {e}")    
        
    def quit_current_game(self):
        """Quit the current game and return to the lobby or connection dialog"""
        if not self.game_active:
            return
            
        # Check if we're in computer play mode or online mode
        computer_mode = hasattr(self, 'computer_ai')
        
        try:
            # Confirm quit
            quit_message = "Are you sure you want to quit this game?"
            if not computer_mode:
                quit_message += " This will end the game for both players."
                
            if not messagebox.askyesno("Quit Game", quit_message):
                return
            
            # If online mode, send quit message to server
            if self.connected and not computer_mode:
                self.socket.send(json.dumps({
                    "type": "quit_game"
                }).encode())
            
            # Reset game state locally
            self.game_active = False
            self.is_my_turn = False
            self.my_color = None
            self.board = chess.Board()  # Reset board to initial position
            self.selected_square = None
            
            # Remove the computer AI reference if it exists
            if computer_mode:
                delattr(self, 'computer_ai')
            
            # Stop any active timers
            self.stop_timer_countdown()
            
            # Update UI
            self.quit_button.config(state=tk.DISABLED)
            
            if computer_mode:
                self.show_info("You have quit the game.")
                # Show connection dialog instead of lobby for computer mode
                self.root.after(500, self.show_connection_dialog)
            else:
                self.show_info("You have quit the game. Returning to lobby...")
                # Show the lobby for online mode
                self.root.after(500, self.show_lobby)
            
            self.draw_board()
            self.update_turn_label()
            
        except Exception as e:
            debug_print(f"Error quitting game: {e}")
            self.show_info(f"Error: {str(e)}")

    def on_closing(self):
        """Handle window close event"""
        if self.connected:
            try:
                self.socket.close()
                self.connected = False
            except:
                pass
        self.root.destroy()
        
    def on_connection_dialog_close(self, dialog):
        """Handle connection dialog close event"""
        if messagebox.askyesno("Quit Application", "Do you want to quit the application?"):
            dialog.destroy()
            self.root.destroy()

    def start_computer_game(self, difficulty):
        """Start a game against the computer with the specified difficulty level"""
        # Import the AI module
        from chess_ai import ChessAI
        
        # Reset the board to initial state
        self.board = chess.Board()
        self.my_color = "white"  # Player always plays as white
        self.is_my_turn = True   # White goes first
        self.game_active = True
        self.selected_square = None
        self.connected = False   # Not connected to server
        
        # Initialize the AI
        self.computer_ai = ChessAI(difficulty)
        
        # Update UI
        self.show_info(f"Playing against Computer ({difficulty} difficulty). You are White.")
        self.update_turn_label()
        self.draw_board()
        
        # Enable the quit button
        self.quit_button.config(state=tk.NORMAL)
        
        # Set up the timer if needed
        self.remaining_time_seconds = 60  # Default to 60 seconds per move
        
        # Show your turn message
        self.add_chat_message("Game started. You're playing as White.")
        self.add_chat_message(f"Computer difficulty: {difficulty.capitalize()}")
        
    def computer_make_move(self):
        """Have the computer make a move"""
        if not hasattr(self, 'computer_ai') or not self.game_active or self.is_my_turn:
            return
            
        # Add a slight delay to make it feel more natural
        self.root.after(500, self._process_computer_move)
    
    def _process_computer_move(self):
        """Process the computer's move calculation and apply it"""
        try:
            # Get the computer's move
            move = self.computer_ai.get_move(self.board)
            
            if move:
                # Apply the move
                self.board.push(move)
                debug_print(f"Computer move: {move}")
                
                # Update UI
                self.is_my_turn = True
                self.add_chat_message(f"Computer played: {move}")
                self.draw_board()
                self.update_turn_label()
                
                # Check for game over conditions
                if self.board.is_checkmate():
                    self.game_active = False
                    self.is_my_turn = False
                    self.show_info("Checkmate! You lost.")
                    self.add_chat_message("Game over: Checkmate! Computer wins.")
                    self.quit_button.config(state=tk.DISABLED)
                    return
                    
                elif self.board.is_stalemate():
                    self.game_active = False
                    self.is_my_turn = False
                    self.show_info("Game drawn by stalemate!")
                    self.add_chat_message("Game over: Draw by stalemate.")
                    self.quit_button.config(state=tk.DISABLED)
                    return
                    
                elif self.board.is_insufficient_material():
                    self.game_active = False
                    self.is_my_turn = False
                    self.show_info("Game drawn - insufficient material!")
                    self.add_chat_message("Game over: Draw by insufficient material.")
                    self.quit_button.config(state=tk.DISABLED)
                    return
                
                # If game is still active, show it's player's turn
                if self.game_active:
                    self.show_info("Your turn to move.")
                    # Start the move timer
                    self.remaining_time_seconds = 60
                    self.start_timer_countdown()
                    
            else:
                debug_print("Computer couldn't find a move")
                self.add_chat_message("Computer couldn't find a move. Something went wrong.")
                
        except Exception as e:
            debug_print(f"Error in computer move: {e}")
            self.add_chat_message(f"Error in computer's move calculation: {str(e)}")

# Main execution block - create and run the application
if __name__ == "__main__":
    root = tk.Tk()
    app = ChessClient(root)
    root.mainloop()
