import socket
import threading
import json
import chess
import time
import uuid

HOST = '0.0.0.0'  # Listen on all available interfaces
PORT = 5555

# Move timer constant - player has 60 seconds to make a move
MOVE_TIMEOUT_SECONDS = 60

lobby = []  # List to track players in the lobby (connection, address)
games = {}  # Dictionary to track active games
waiting_games = {}  # Dictionary to track games waiting for players {game_id: game_session}
spectators = {}  # Dictionary to track spectators watching games
lock = threading.Lock()  # Thread lock for shared resources

# Debug flag for verbose logging
DEBUG = True


def debug_print(message):
    """Print debug messages if DEBUG is enabled"""
    if DEBUG:
        print(f"[DEBUG] {message}")


def broadcast_lobby():
    """Broadcast lobby state to all players in the lobby"""
    lobby_state = {
        "type": "lobby_update",
        "players": [addr[0] for conn, addr in lobby],
        "available_games": [
            {"id": game_id, "creator": game.creator_address[0], "is_private": game.is_private} 
            for game_id, game in waiting_games.items()
        ]
    }
    
    for conn, _ in lobby:
        try:
            conn.send(json.dumps(lobby_state).encode())
        except Exception as e:
            debug_print(f"Error sending lobby update: {e}")


class GameSession:
    def __init__(self, white_conn=None, black_conn=None, creator_conn=None, creator_addr=None, password=None):
        self.board = chess.Board()
        self.white_conn = white_conn
        self.black_conn = black_conn
        self.players = {}
        if white_conn:
            self.players[chess.WHITE] = white_conn
        if black_conn:
            self.players[chess.BLACK] = black_conn
        self.turn = chess.WHITE  # White starts first
        self.spectators = []  # List to track spectators for this game
        self.game_id = str(uuid.uuid4())[:8]  # Generate a shorter, readable unique ID
        self.last_move_time = time.time()  # Track when the last move was made
        self.creator_conn = creator_conn  # Store the creator's connection
        self.creator_address = creator_addr  # Store the creator's address
        self.password = password  # Optional password protection
        self.is_private = password is not None  # Flag to indicate if the game is private

        debug_print(f"Created new game session with ID {self.game_id}{' (private)' if self.is_private else ''}")

    def opponent(self, conn):
        """Return the opponent's connection for a given player connection"""
        return self.black_conn if conn == self.white_conn else self.white_conn

    def broadcast(self, data):
        """Send data to both players and all spectators"""
        msg = json.dumps(data).encode()
        debug_print(f"Broadcasting: {data}")

        # Send to players
        for conn in [self.white_conn, self.black_conn]:
            try:
                conn.send(msg)
                debug_print(f"Sent to {'white' if conn == self.white_conn else 'black'} player")
            except Exception as e:
                print(f"Error sending to player: {e}")
                continue

        # Send to spectators
        for spectator in self.spectators:
            try:
                spectator.send(msg)
            except Exception as e:
                print(f"Error sending to spectator: {e}")
                continue

    def add_spectator(self, conn):
        """Add a spectator to this game session"""
        self.spectators.append(conn)
        # Send the current state to the new spectator
        try:
            conn.send(json.dumps({
                "type": "info",
                "msg": f"You are now spectating Game #{self.game_id}"
            }).encode())
            conn.send(json.dumps({
                "type": "board",
                "board": self.board.fen()
            }).encode())
            conn.send(json.dumps({
                "type": "turn",
                "turn": "White" if self.turn == chess.WHITE else "Black"
            }).encode())
        except Exception as e:
            print(f"Error sending initial state to spectator: {e}")

    def next_turn(self):
        """Switch turns and notify all clients"""
        self.turn = chess.BLACK if self.turn == chess.WHITE else chess.WHITE
        # Reset the move timer for the new player's turn
        self.last_move_time = time.time()

        # Check for game end conditions
        game_status = "active"
        if self.board.is_checkmate():
            winner = "Black" if self.turn == chess.WHITE else "White"
            self.broadcast({"type": "info", "msg": f"Checkmate! {winner} wins!"})
            game_status = "ended"
        elif self.board.is_stalemate():
            self.broadcast({"type": "info", "msg": "Stalemate! Game ends in a draw."})
            game_status = "ended"
        elif self.board.is_insufficient_material():
            self.broadcast({"type": "info", "msg": "Draw due to insufficient material."})
            game_status = "ended"

        # Notify players about the next turn and the board state
        self.broadcast({
            "type": "turn",
            "turn": "White" if self.turn == chess.WHITE else "Black",
            "status": game_status,
            "time_limit": MOVE_TIMEOUT_SECONDS  # Send the time limit to clients
        })
        self.broadcast({"type": "board", "board": self.board.fen()})

        return game_status


def handle_client(conn, addr):
    """Handle a connected client (player or spectator)"""
    global lobby, games, waiting_games, spectators
    print(f"[NEW CONNECTION] {addr} connected.")
    assigned_role = None  # Will be 'player' or 'spectator'

    try:
        # First message from client should indicate if they want to play or spectate
        data = conn.recv(2048).decode()        
        if not data:
            print(f"No initial data received from {addr}, disconnecting.")
            return
            
        debug_print(f"Received from {addr}: {data}")
        msg = json.loads(data)
        if msg.get("type") == "join":
            role = msg.get("role", "player")  # Default to player if not specified
            debug_print(f"Client at {addr} is joining as {role}")
            
            with lock:
                if role == "player":
                    # Add player to the lobby
                    lobby.append((conn, addr))
                    assigned_role = "player"
                    conn.send(json.dumps({"type": "info", "msg": "Joined lobby. Create or join a game."}).encode())
                    
                    # Broadcast updated lobby state to all players
                    broadcast_lobby()
                        
                elif role == "spectator":
                    # Handle spectator connection
                    assigned_role = "spectator"
                    game_id = msg.get("game_id")

                    # Find the requested game
                    target_game = None
                    for game in set(games.values()):
                        if game.game_id == game_id:
                            target_game = game
                            break

                    if target_game:
                        target_game.add_spectator(conn)
                        spectators[conn] = target_game
                    else:
                        # No game found with that ID
                        active_games = [g.game_id for g in set(games.values())]
                        conn.send(json.dumps({
                            "type": "info",
                            "msg": f"Game #{game_id} not found. Active games: {active_games}"
                        }).encode())
        else:
            conn.send(json.dumps({"type": "error", "msg": "First message must be a join request"}).encode())
            return

        # Main client handling loop
        while True:
            data = conn.recv(2048).decode()
            if not data:
                debug_print(f"No data received from {addr}, breaking connection loop.")
                break
                
            debug_print(f"Received from {addr}: {data}")
            msg = json.loads(data)
            
            # Handle lobby actions first (for players in the lobby)
            if msg.get("type") == "create_game" and assigned_role == "player" and (conn, addr) in lobby:
                with lock:
                    # Get password if provided (for private games)
                    password = msg.get("password", None)
                    
                    # Create a new game with the player as white
                    debug_print(f"Player {addr} is creating a game. Private: {password is not None}")
                    game = GameSession(white_conn=conn, creator_conn=conn, creator_addr=addr, password=password)
                    waiting_games[game.game_id] = game
                    lobby.remove((conn, addr))
                    games[conn] = game
                      # Notify the player
                    private_msg = " (Private game)" if password else ""
                    conn.send(json.dumps({
                        "type": "info",
                        "msg": f"Game #{game.game_id}{private_msg} created. You are White. Waiting for an opponent..."
                    }).encode())
                    
                    # Broadcast updated lobby state to all players
                    broadcast_lobby()
                    continue
                
            elif msg.get("type") == "join_game" and assigned_role == "player" and (conn, addr) in lobby:
                game_id = msg.get("game_id")
                with lock:
                    if game_id in waiting_games:
                        game = waiting_games[game_id]
                        
                        # Check if game is password protected
                        if game.is_private:
                            provided_password = msg.get("password", "")
                            if provided_password != game.password:
                                conn.send(json.dumps({
                                    "type": "error",
                                    "msg": "Incorrect password for private game."
                                }).encode())
                                continue
                        game.black_conn = conn
                        game.players[chess.BLACK] = conn
                        game.black_addr = addr  # Store black player's address
                        
                        # Add this player to the game
                        games[conn] = game
                        
                        # Remove the game from waiting list
                        del waiting_games[game_id]
                        
                        # Remove player from lobby
                        lobby.remove((conn, addr))
                        
                        # Notify both players
                        creator_conn = game.white_conn
                        creator_conn.send(json.dumps({
                            "type": "info",
                            "msg": f"Game #{game.game_id} started. You are White."
                        }).encode())
                        
                        conn.send(json.dumps({
                            "type": "info",
                            "msg": f"Game #{game.game_id} started. You are Black."
                        }).encode())
                        
                        # Set initial game state
                        game.broadcast({"type": "turn", "turn": "White"})
                        game.broadcast({"type": "board", "board": game.board.fen()})
                        
                        # Reset move timer for the first player's turn
                        game.last_move_time = time.time()
                        
                        # Broadcast updated lobby state to all players
                        broadcast_lobby()
                        continue
                    else:
                        conn.send(json.dumps({
                            "type": "error",
                            "msg": f"Game #{game_id} not found or already full."
                        }).encode())
                        continue
                        
            elif msg.get("type") == "lobby_request" and assigned_role == "player":
                # Player is requesting a lobby update
                with lock:
                    broadcast_lobby()
                continue

            # Handle player in a game
            if assigned_role == "player" and conn in games:
                game = games.get(conn)
                
                if msg["type"] == "move":
                    player_color = chess.WHITE if conn == game.white_conn else chess.BLACK

                    # Check if it's this player's turn
                    if game.turn != player_color:
                        debug_print(f"Not {player_color}'s turn")
                        conn.send(json.dumps({
                            "type": "error",
                            "msg": "Not your turn"
                        }).encode())
                        continue

                    try:
                        move = chess.Move.from_uci(msg["move"])
                        debug_print(f"Processing move: {move}")

                        # Validate the move
                        if move in game.board.legal_moves:
                            game.board.push(move)
                            game.broadcast({"type": "move", "move": msg["move"], "board": game.board.fen()})
                            game_status = game.next_turn()  # Switch turn after valid move                            # If the game ended, clean up
                            if game_status == "ended":
                                with lock:
                                    debug_print(f"Game {game.game_id} ended, cleaning up")
                                    
                                    # Clean up game references
                                    white_conn = game.white_conn
                                    black_conn = game.black_conn
                                    white_addr = game.creator_address
                                    black_addr = getattr(game, 'black_addr', None)
                                    
                                    # Remove from games dictionary
                                    if white_conn in games:
                                        del games[white_conn]
                                    if black_conn in games:
                                        del games[black_conn]
                                    
                                    # Add players back to lobby if they're still connected
                                    if white_conn and white_addr:
                                        lobby.append((white_conn, white_addr))
                                        white_conn.send(json.dumps({
                                            "type": "info",
                                            "msg": "Game ended. You have been returned to the lobby."
                                        }).encode())
                                    
                                    if black_conn and black_addr:
                                        lobby.append((black_conn, black_addr))
                                        black_conn.send(json.dumps({
                                            "type": "info",
                                            "msg": "Game ended. You have been returned to the lobby."
                                        }).encode())
                                    
                                    # Update lobby for everyone
                                    broadcast_lobby()

                        else:
                            debug_print(f"Illegal move: {move}")
                            conn.send(json.dumps({
                                "type": "error",
                                "msg": "Illegal move"
                            }).encode())
                    except Exception as e:
                        debug_print(f"Error processing move: {e}")
                        conn.send(json.dumps({
                            "type": "error",
                            "msg": f"Invalid move format: {str(e)}"                        }).encode())
                        
                elif msg["type"] == "chat":
                    if game:
                        sender = "White" if conn == game.white_conn else "Black"
                        chat_msg = f"{sender}: {msg['msg']}"
                        game.broadcast({"type": "chat", "msg": chat_msg})
                        
                elif msg["type"] == "quit_game":
                    # Player wants to quit the game and return to lobby
                    if conn in games and games[conn] == game:
                        player_color = "White" if conn == game.white_conn else "Black"
                        debug_print(f"{player_color} player has quit game {game.game_id}")
                        
                        # Notify the opponent
                        opponent = game.opponent(conn)
                        if opponent:
                            opponent.send(json.dumps({
                                "type": "game_over",
                                "result": f"{player_color} player has quit the game.",
                                "reason": "quit"
                            }).encode())
                        
                        # Notify spectators
                        for spec in game.spectators:
                            try:
                                spec.send(json.dumps({
                                    "type": "game_over",
                                    "result": f"{player_color} player has quit the game.",
                                    "reason": "quit"
                                }).encode())
                            except:
                                pass
                        
                        # Move both players back to lobby
                        with lock:
                            # Get opponent's address - need this for adding to lobby
                            opponent_addr = None
                            if opponent == game.white_conn:
                                opponent_addr = game.creator_address
                            elif opponent and hasattr(game, 'black_addr'):
                                opponent_addr = game.black_addr
                            
                            # Remove game reference from both players
                            del games[conn]
                            if opponent and opponent in games:
                                del games[opponent]
                            
                            # Add quitting player back to lobby
                            lobby.append((conn, addr))
                            
                            # Add opponent back to lobby if they're still connected
                            if opponent and opponent_addr:
                                lobby.append((opponent, opponent_addr))
                                # Notify the opponent they're back in the lobby
                                try:
                                    opponent.send(json.dumps({
                                        "type": "info",
                                        "msg": "Your opponent has quit the game. You have been returned to the lobby."
                                    }).encode())
                                except Exception as e:
                                    debug_print(f"Error notifying opponent: {e}")
                            
                            # Notify the quitting player
                            conn.send(json.dumps({
                                "type": "info",
                                "msg": "You have quit the game. Returning to lobby."
                            }).encode())
                            
                            # Update lobby for everyone
                            broadcast_lobby()
                        
            elif assigned_role == "spectator":
                game = spectators.get(conn)
                if not game:
                    continue
                    
                if msg["type"] == "chat":
                    # Spectators can chat too
                    chat_msg = f"Spectator: {msg['msg']}"
                    game.broadcast({"type": "chat", "msg": chat_msg})

    except Exception as e:
        print(f"Error handling client {addr}: {e}")
    finally:
        print(f"[DISCONNECTION] {addr} disconnected.")

        with lock:
            # Clean up based on role
            if assigned_role == "player":
                # Remove from lobby if still there
                if (conn, addr) in lobby:
                    lobby.remove((conn, addr))
                    # Broadcast updated lobby
                    broadcast_lobby()

                # Check if the player created a waiting game
                game_to_remove = None
                for game_id, game in waiting_games.items():
                    if game.creator_conn == conn:
                        game_to_remove = game_id
                        break
                    
                if game_to_remove:
                    del waiting_games[game_to_remove]
                    # Broadcast updated lobby
                    broadcast_lobby()                # Handle game cleanup if in a game
                if conn in games:
                    game = games[conn]
                    other = game.opponent(conn)
                    
                    # Get opponent's address for adding them back to the lobby
                    other_addr = None
                    if other == game.white_conn:
                        other_addr = game.creator_address
                    elif other and hasattr(game, 'black_addr'):
                        other_addr = game.black_addr

                    # Notify opponent of disconnection
                    if other:
                        try:
                            other.send(json.dumps({
                                "type": "info",
                                "msg": "Opponent disconnected. Game ended."
                            }).encode())
                            
                            # Also send a game_over message to properly reset client state
                            other.send(json.dumps({
                                "type": "game_over",
                                "result": "Opponent disconnected.",
                                "reason": "disconnection"
                            }).encode())
                        except Exception as e:
                            debug_print(f"Error notifying opponent of disconnection: {e}")

                    # Clean up the game
                    del games[conn]
                    if other and other in games:
                        del games[other]
                        
                    # Add opponent back to lobby if they're still connected
                    if other and other_addr:
                        lobby.append((other, other_addr))
                        debug_print(f"Added opponent back to lobby after disconnection")

                    # Notify spectators
                    for spec in game.spectators:
                        try:
                            spec.send(json.dumps({
                                "type": "info",
                                "msg": "Game ended due to player disconnection."
                            }).encode())
                            if spec in spectators:
                                del spectators[spec]
                        except:
                            pass
                    
                    # Broadcast lobby update to all players
                    broadcast_lobby()

            elif assigned_role == "spectator":
                if conn in spectators:
                    del spectators[conn]

        # Close connection
        try:
            conn.close()
        except:
            pass


def list_games():
    """Return a list of active games for lobby display"""
    active_games = []
    
    # Add games that are waiting for players
    for game_id, game in waiting_games.items():
        active_games.append({
            "id": game_id,
            "status": "waiting",
            "creator": game.creator_address[0] if game.creator_address else "Unknown"
        })
    
    # Add active games
    for game in set(games.values()):
        if game.white_conn and game.black_conn:  # Only include games with both players
            active_games.append({
                "id": game.game_id,
                "status": "active",
                "white_to_move": game.turn == chess.WHITE
            })
    
    return active_games


def check_move_timers():
    """Check for move timeouts in active games"""
    debug_print("Starting move timer check thread")

    while True:
        time.sleep(1)
        current_time = time.time()

        with lock:
            active_games = list(set(games.values()))

            for game in active_games:
                if not hasattr(game, 'last_move_time') or game.last_move_time is None:
                    continue

                elapsed_time = current_time - game.last_move_time
                if elapsed_time > MOVE_TIMEOUT_SECONDS:
                    # Get the player who timed out
                    timed_out_player = game.players.get(game.turn)
                    if not timed_out_player:
                        continue  # No player connection found

                    # Get the opponent
                    opponent_color = chess.BLACK if game.turn == chess.WHITE else chess.WHITE
                    opponent = game.players.get(opponent_color)

                    # Current player color string
                    player_color = "White" if game.turn == chess.WHITE else "Black"

                    debug_print(f"Move timeout in game {game.game_id} for {player_color}")

                    # Option 1: End the game (uncomment this block if you want timeouts to end the game)
                    """
                    # Send game over message
                    game.broadcast({
                        "type": "game_over",
                        "result": f"{player_color} player timed out. {('Black' if player_color == 'White' else 'White')} wins!",
                        "reason": "timeout"
                    })

                    # Clean up the game
                    if timed_out_player in games:
                        del games[timed_out_player]
                    if opponent and opponent in games:
                        del games[opponent]
                    """  # Option 2: Continue playing by switching turn to opponent
                    debug_print(f"Timeout for {player_color}. Current board state: {game.board.fen()}")

                    game.broadcast({
                        "type": "info",
                        "msg": f"{player_color} took too long. Turn passes to opponent."
                    })

                    # Important: Reset move timer and properly switch turn
                    game.last_move_time = time.time()
                    game.turn = opponent_color

                    # Send a clear board reset command - this will force clients to fully synchronize
                    # We'll use a new message type to explicitly handle timeouts
                    game.broadcast({
                        "type": "timeout_sync",
                        "timeout_player": player_color,
                        "board": game.board.fen(),
                        "next_turn": "Black" if opponent_color == chess.BLACK else "White"
                    })

                    # Send the current board state to ensure clients are in sync
                    game.broadcast({
                        "type": "board",
                        "board": game.board.fen()
                    })

                    # Send updated turn information with all required fields
                    game.broadcast({
                        "type": "turn",
                        "turn": "Black" if opponent_color == chess.BLACK else "White",
                        "status": "active",
                        "time_limit": MOVE_TIMEOUT_SECONDS
                    })


def start_server():
    """Initialize the server and start listening for connections"""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # Allow address reuse

    try:
        try:
            server.bind((HOST, PORT))
            server.listen(10)  # Allow up to 10 waiting connections
            print(f"[SERVER STARTED] Listening on {HOST}:{PORT}")
        except OSError as e:
            print(f"[BIND ERROR] Could not bind to {HOST}:{PORT}: {e}")
            if "already in use" in str(e):
                print("The port is already in use. Make sure no other instance of the server is running.")
            return
        
        # Start the move timer checker thread
        timer_thread = threading.Thread(target=check_move_timers, daemon=True)
        timer_thread.start()

        while True:
            try:
                conn, addr = server.accept()
                print(f"[NEW CONNECTION] Accepted connection from {addr}")
                thread = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
                thread.start()
                print(f"[ACTIVE CONNECTIONS] {threading.active_count() - 1}")
                print(f"[PLAYERS IN LOBBY] {len(lobby)}")
                print(f"[ACTIVE GAMES] {len(set(games.values()))}")
                print(f"[WAITING GAMES] {len(waiting_games)}")
            except Exception as e:
                print(f"[CONNECTION ERROR] Error accepting connection: {e}")
                # Continue listening for other connections even if one fails

    except KeyboardInterrupt:
        print("[SERVER] Server shutdown requested by user")
    except Exception as e:
        print(f"[SERVER ERROR] {e}")
    finally:
        server.close()
        print("[SERVER STOPPED]")


if __name__ == "__main__":
    start_server()