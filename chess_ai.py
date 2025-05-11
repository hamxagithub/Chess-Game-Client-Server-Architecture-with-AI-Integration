"""
Chess AI module for the client application.
Provides computer player capabilities with multiple difficulty levels.
"""

import chess
import random
import time

class ChessAI:
    def __init__(self, difficulty='medium'):
        """
        Initialize the chess AI with the specified difficulty level.
        
        Args:
            difficulty (str): 'easy', 'medium', or 'hard'
        """
        self.difficulty = difficulty.lower()
        # Set search depth based on difficulty
        if self.difficulty == 'easy':
            self.depth = 1
        elif self.difficulty == 'medium':
            self.depth = 2
        elif self.difficulty == 'hard':
            self.depth = 3
        else:
            # Default to medium if invalid difficulty
            self.depth = 2
            self.difficulty = 'medium'

    def get_move(self, board):
        """
        Get the best move for the current board position.
        
        Args:
            board (chess.Board): The current chess board position
            
        Returns:
            chess.Move: The chosen move
        """
        # Add a slight delay to make the game feel more natural
        time.sleep(0.5)
        
        if self.difficulty == 'easy':
            return self._get_random_move(board)
        else:
            # Use minimax with alpha-beta pruning for medium and hard
            best_move = self._minimax_root(board, self.depth)
            return best_move

    def _get_random_move(self, board):
        """Get a random legal move with some basic logic for easy difficulty."""
        legal_moves = list(board.legal_moves)
        
        # Categorize moves
        captures = []
        checks = []
        other_moves = []
        
        for move in legal_moves:
            # If it's a capture, add to captures list
            if board.is_capture(move):
                captures.append(move)
            else:
                # Test if the move gives check
                board.push(move)
                gives_check = board.is_check()
                board.pop()
                
                if gives_check:
                    checks.append(move)
                else:
                    other_moves.append(move)
        
        # Prioritize moves with a bit of randomness
        if captures and random.random() < 0.7:  # 70% chance to choose a capture if available
            return random.choice(captures)
        elif checks and random.random() < 0.5:  # 50% chance to choose a check if available
            return random.choice(checks)
        else:
            return random.choice(legal_moves)  # Otherwise random move

    def _minimax_root(self, board, depth):
        """Root of the minimax algorithm to find the best move."""
        legal_moves = list(board.legal_moves)
        
        # If no legal moves, return None
        if not legal_moves:
            return None
            
        best_move = legal_moves[0]
        best_value = float('-inf')
        alpha = float('-inf')
        beta = float('inf')
        
        for move in legal_moves:
            board.push(move)
            value = -self._minimax(board, depth - 1, -beta, -alpha, False if board.turn else True)
            board.pop()
            
            if value > best_value:
                best_value = value
                best_move = move
            
            alpha = max(alpha, value)
        
        return best_move

    def _minimax(self, board, depth, alpha, beta, is_maximizing):
        """
        Minimax algorithm with alpha-beta pruning.
        
        Args:
            board: The chess board
            depth: Remaining depth to search
            alpha: Alpha value for pruning
            beta: Beta value for pruning
            is_maximizing: Whether we're maximizing or minimizing
        """
        if depth == 0 or board.is_game_over():
            return self._evaluate_board(board)
        
        if is_maximizing:
            value = float('-inf')
            for move in board.legal_moves:
                board.push(move)
                value = max(value, self._minimax(board, depth - 1, alpha, beta, False))
                board.pop()
                alpha = max(alpha, value)
                if alpha >= beta:
                    break  # Beta cutoff
            return value
        else:
            value = float('inf')
            for move in board.legal_moves:
                board.push(move)
                value = min(value, self._minimax(board, depth - 1, alpha, beta, True))
                board.pop()
                beta = min(beta, value)
                if alpha >= beta:
                    break  # Alpha cutoff
            return value

    def _evaluate_board(self, board):
        """
        Evaluate the board position.
        
        Args:
            board: The chess board to evaluate
            
        Returns:
            float: Score for the position (positive is good for white)
        """
        if board.is_checkmate():
            # Checkmate is the best/worst outcome
            return -10000 if board.turn else 10000
            
        if board.is_stalemate() or board.is_insufficient_material():
            return 0  # Draw
        
        # Piece values
        piece_values = {
            chess.PAWN: 100,
            chess.KNIGHT: 320,
            chess.BISHOP: 330,
            chess.ROOK: 500,
            chess.QUEEN: 900,
            chess.KING: 20000
        }
        
        # Position evaluation tables for improved piece positioning
        pawn_table = [
            0,  0,  0,  0,  0,  0,  0,  0,
            5, 10, 10,-20,-20, 10, 10,  5,
            5, -5,-10,  0,  0,-10, -5,  5,
            0,  0,  0, 20, 20,  0,  0,  0,
            5,  5, 10, 25, 25, 10,  5,  5,
            10, 10, 20, 30, 30, 20, 10, 10,
            50, 50, 50, 50, 50, 50, 50, 50,
            0,  0,  0,  0,  0,  0,  0,  0
        ]
        
        knight_table = [
            -50,-40,-30,-30,-30,-30,-40,-50,
            -40,-20,  0,  5,  5,  0,-20,-40,
            -30,  5, 10, 15, 15, 10,  5,-30,
            -30,  0, 15, 20, 20, 15,  0,-30,
            -30,  5, 15, 20, 20, 15,  5,-30,
            -30,  0, 10, 15, 15, 10,  0,-30,
            -40,-20,  0,  0,  0,  0,-20,-40,
            -50,-40,-30,-30,-30,-30,-40,-50
        ]
        
        bishop_table = [
            -20,-10,-10,-10,-10,-10,-10,-20,
            -10,  5,  0,  0,  0,  0,  5,-10,
            -10, 10, 10, 10, 10, 10, 10,-10,
            -10,  0, 10, 10, 10, 10,  0,-10,
            -10,  5,  5, 10, 10,  5,  5,-10,
            -10,  0,  5, 10, 10,  5,  0,-10,
            -10,  0,  0,  0,  0,  0,  0,-10,
            -20,-10,-10,-10,-10,-10,-10,-20
        ]
        
        rook_table = [
            0,  0,  0,  5,  5,  0,  0,  0,
            -5,  0,  0,  0,  0,  0,  0, -5,
            -5,  0,  0,  0,  0,  0,  0, -5,
            -5,  0,  0,  0,  0,  0,  0, -5,
            -5,  0,  0,  0,  0,  0,  0, -5,
            -5,  0,  0,  0,  0,  0,  0, -5,
            5, 10, 10, 10, 10, 10, 10,  5,
            0,  0,  0,  0,  0,  0,  0,  0
        ]
        
        queen_table = [
            -20,-10,-10, -5, -5,-10,-10,-20,
            -10,  0,  5,  0,  0,  0,  0,-10,
            -10,  5,  5,  5,  5,  5,  0,-10,
            0,  0,  5,  5,  5,  5,  0, -5,
            -5,  0,  5,  5,  5,  5,  0, -5,
            -10,  0,  5,  5,  5,  5,  0,-10,
            -10,  0,  0,  0,  0,  0,  0,-10,
            -20,-10,-10, -5, -5,-10,-10,-20
        ]
        
        king_middlegame_table = [
            20, 30, 10,  0,  0, 10, 30, 20,
            20, 20,  0,  0,  0,  0, 20, 20,
            -10,-20,-20,-20,-20,-20,-20,-10,
            -20,-30,-30,-40,-40,-30,-30,-20,
            -30,-40,-40,-50,-50,-40,-40,-30,
            -30,-40,-40,-50,-50,-40,-40,-30,
            -30,-40,-40,-50,-50,-40,-40,-30,
            -30,-40,-40,-50,-50,-40,-40,-30
        ]
        
        piece_tables = {
            chess.PAWN: pawn_table,
            chess.KNIGHT: knight_table,
            chess.BISHOP: bishop_table,
            chess.ROOK: rook_table,
            chess.QUEEN: queen_table,
            chess.KING: king_middlegame_table
        }
        
        # Calculate material and position score
        score = 0
        
        # Loop through all pieces
        for square in chess.SQUARES:
            piece = board.piece_at(square)
            if piece:
                # Material value
                value = piece_values[piece.piece_type] * (1 if piece.color == chess.WHITE else -1)
                
                # Position value (flipped for black)
                if piece.color == chess.WHITE:
                    position_value = piece_tables[piece.piece_type][63 - square]
                else:
                    position_value = piece_tables[piece.piece_type][square] * -1
                
                score += value + position_value
        
        # Mobility bonus (number of legal moves)
        current_turn = board.turn
        
        # Count legal moves for the current player
        board.turn = chess.WHITE
        white_moves = len(list(board.legal_moves))
        
        board.turn = chess.BLACK
        black_moves = len(list(board.legal_moves))
        
        # Restore the original turn
        board.turn = current_turn
        
        score += (white_moves - black_moves) * 5  # Small bonus per extra move
        
        return score
