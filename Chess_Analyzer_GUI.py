#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import tkinter as tk
from tkinter import messagebox, filedialog
import tkinter.font as tkfont

import chess
import chess.engine

import asyncio
import threading
import queue
import os
import shutil
import sys


class ChessAnalyzerApp:
    def __init__(self, master: tk.Tk):
        self.master = master
        master.title("Chess Analyzer and Board")
        master.geometry("1000x700")
        master.resizable(True, True)

        # --- Theme ---
        self.themes = {
            "dark": {
                "bg": "#1e1f22",
                "panel": "#2b2d31",
                "panel_alt": "#232428",
                "text": "#e6e6e6",
                "muted": "#b5b5b5",
                "entry_bg": "#1b1c1f",
                "button_bg": "#3a3d45",
                "button_active_bg": "#4a4e59",
                "button_fg": "#ffffff",
                "accent": "#6ea8fe",
                "success": "#57d163",
                "warning": "#fbbc04",
                "error": "#ff6b6b",
                "canvas_bg": "#1e1f22",
                # Board is kept "classic" (high readability for pieces), slightly tuned for dark UI.
                "board_light": "#DDB88C",
                "board_dark": "#A66D4F",
                "coord_fg": "#e6e6e6",
            },
            "light": {
                "bg": "#f7f7f8",
                "panel": "#ffffff",
                "panel_alt": "#f2f3f5",
                "text": "#111111",
                "muted": "#555555",
                "entry_bg": "#ffffff",
                "button_bg": "#e6e6e8",
                "button_active_bg": "#d6d7da",
                "button_fg": "#111111",
                "accent": "#1f6feb",
                "success": "#0a7a2f",
                "warning": "#b25e00",
                "error": "#b00020",
                "canvas_bg": "#f7f7f8",
                "board_light": "#DDB88C",
                "board_dark": "#A66D4F",
                "coord_fg": "#111111",
            },
        }
        self.theme = "dark"

        # --- Chess state and GUI ---
        self.board = chess.Board()
        self.board_flipped = False
        self.square_size = 60
        self.selected_square = None
        self.legal_moves_highlight = []

        # Choose a Unicode-capable font (Linux often lacks Arial).
        self.piece_font_family = self._detect_piece_font_family()

        # --- Engine and threading ---
        self.engine = None
        self.engine_thread = None
        self.request_queue: "queue.Queue[tuple[str, object]]" = queue.Queue()
        self.result_queue: "queue.Queue[tuple[str, object]]" = queue.Queue()

        self._create_widgets()
        self._apply_theme()
        self._draw_board()
        self._start_engine_thread()
        self._check_result_queue()

        self.master.protocol("WM_DELETE_WINDOW", self._on_closing)

    # ----------------------------
    # Theme helpers
    # ----------------------------
    def _palette(self) -> dict:
        return self.themes[self.theme]

    def _set_status(self, text: str, kind: str = "info"):
        p = self._palette()
        color = {
            "info": p["accent"],
            "success": p["success"],
            "warning": p["warning"],
            "error": p["error"],
            "muted": p["muted"],
        }.get(kind, p["accent"])
        self.status_label.config(text=text, fg=color)

    def _toggle_theme(self):
        self.theme = "light" if self.theme == "dark" else "dark"
        self._apply_theme()
        self._draw_board()

        # Re-tint the status label to match theme while preserving message.
        current = self.status_label.cget("text")
        self._set_status(current, "info")

    def _apply_theme(self):
        p = self._palette()
        self.master.configure(bg=p["bg"])

        # Recursively apply to all widgets
        def apply(widget: tk.Widget):
            wclass = widget.winfo_class()

            try:
                if wclass in ("Frame", "TFrame"):
                    widget.configure(bg=p["bg"])
                elif wclass in ("Labelframe", "LabelFrame"):
                    widget.configure(bg=p["panel"], fg=p["text"], highlightthickness=0)
                elif wclass in ("Label", "TLabel"):
                    widget.configure(bg=p["panel"], fg=p["text"])
                elif wclass in ("Entry", "TEntry"):
                    widget.configure(
                        bg=p["entry_bg"],
                        fg=p["text"],
                        insertbackground=p["text"],
                        relief="flat",
                        highlightthickness=1,
                        highlightbackground=p["panel_alt"],
                        highlightcolor=p["accent"],
                    )
                elif wclass in ("Button", "TButton"):
                    widget.configure(
                        bg=p["button_bg"],
                        fg=p["button_fg"],
                        activebackground=p["button_active_bg"],
                        activeforeground=p["button_fg"],
                        relief="flat",
                        highlightthickness=0,
                        bd=0,
                    )
                elif wclass in ("Canvas",):
                    widget.configure(bg=p["canvas_bg"], highlightthickness=0)
                elif wclass in ("Checkbutton", "Radiobutton"):
                    widget.configure(bg=p["panel"], fg=p["text"], activebackground=p["panel"])
                else:
                    # Fall back gently
                    if "bg" in widget.configure():
                        widget.configure(bg=p["panel"])
                    if "fg" in widget.configure():
                        widget.configure(fg=p["text"])
            except Exception:
                pass

            for child in widget.winfo_children():
                apply(child)

        apply(self.master)

        # Tweak specific container backgrounds
        self.controls_frame.configure(bg=p["bg"])
        self.main_frame.configure(bg=p["bg"])
        self.board_frame.configure(bg=p["bg"])

        # LabelFrames should be panels
        for lf in (self.sf_frame, self.fen_frame, self.analysis_frame):
            lf.configure(bg=p["panel"], fg=p["text"])

        self.canvas.configure(bg=p["canvas_bg"])

        # Semantic labels
        if self.engine is None:
            self.sf_status_label.configure(text="Status: Not connected", fg=p["error"], bg=p["panel"])
        else:
            self.sf_status_label.configure(text="Status: Connected!", fg=p["success"], bg=p["panel"])

        self.player_label.configure(bg=p["panel"], fg=p["text"])
        self.best_move_label.configure(bg=p["panel"], fg=p["text"])
        self.evaluation_label.configure(bg=p["panel"], fg=p["text"])

    # ----------------------------
    # UI helpers / platform glue
    # ----------------------------
    def _detect_piece_font_family(self) -> str:
        """Pick a font that typically contains Unicode chess piece glyphs on Linux/macOS/Windows."""
        try:
            families = set(tkfont.families())
        except Exception:
            families = set()

        preferred = [
            "DejaVu Sans",
            "DejaVu Sans Mono",
            "Noto Sans Symbols2",
            "Noto Sans Symbols",
            "Symbola",
            "Segoe UI Symbol",
            "Apple Symbols",
            "Arial Unicode MS",
            "Arial",
        ]
        for f in preferred:
            if f in families:
                return f
        return "TkDefaultFont"

    def _find_stockfish_in_path(self) -> str | None:
        return shutil.which("stockfish-ubuntu-x86-64-avx2")

    def _resolve_engine_path(self, user_value: str) -> str | None:
        if not user_value:
            return None

        if os.path.isfile(user_value):
            if os.access(user_value, os.X_OK):
                return os.path.abspath(user_value)
            return None

        resolved = shutil.which(user_value)
        if resolved and os.path.isfile(resolved) and os.access(resolved, os.X_OK):
            return resolved

        return None

    # ----------------------------
    # Widget creation
    # ----------------------------
    def _create_widgets(self):
        self.main_frame = tk.Frame(self.master)
        self.main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.board_frame = tk.Frame(self.main_frame)
        self.board_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.controls_frame = tk.Frame(self.main_frame, width=400)
        self.controls_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=(10, 0))
        self.controls_frame.pack_propagate(False)

        self.canvas = tk.Canvas(self.board_frame, width=self.square_size * 8 + 40, height=self.square_size * 8 + 40)
        self.canvas.pack(anchor="center", pady=20)
        self.canvas.bind("<Button-1>", self._on_square_click)

        self.sf_frame = tk.LabelFrame(self.controls_frame, text="Stockfish Engine Setup", padx=10, pady=10)
        self.sf_frame.pack(pady=10, padx=10, fill="x")

        tk.Label(self.sf_frame, text="Executable (path or command):").grid(row=0, column=0, sticky="w", pady=2)

        self.stockfish_path_var = tk.StringVar(self.master)
        self.stockfish_path_entry = tk.Entry(self.sf_frame, textvariable=self.stockfish_path_var, width=30)
        self.stockfish_path_entry.grid(row=1, column=0, padx=0, pady=2, sticky="ew")

        self.browse_button = tk.Button(self.sf_frame, text="Browse", command=self._browse_stockfish)
        self.browse_button.grid(row=1, column=1, padx=5, pady=2)

        self.connect_button = tk.Button(self.sf_frame, text="Connect to Stockfish", command=self._connect_to_stockfish)
        self.connect_button.grid(row=2, column=0, columnspan=2, pady=5, sticky="ew")

        self.sf_status_label = tk.Label(self.sf_frame, text="Status: Not connected")
        self.sf_status_label.grid(row=3, column=0, columnspan=2, pady=2)

        self.sf_frame.grid_columnconfigure(0, weight=1)

        self.fen_frame = tk.LabelFrame(self.controls_frame, text="Board State (FEN)", padx=10, pady=10)
        self.fen_frame.pack(pady=10, padx=10, fill="x")

        self.fen_var = tk.StringVar(self.master, value=self.board.fen())
        self.fen_entry = tk.Entry(self.fen_frame, textvariable=self.fen_var, width=40)
        self.fen_entry.pack(fill="x", pady=(0, 5))

        reset_button = tk.Button(self.fen_frame, text="Reset Board to FEN", command=self._reset_board_from_fen)
        reset_button.pack(fill="x", pady=(0, 5))

        flip_button = tk.Button(self.fen_frame, text="Flip Board", command=self._flip_board)
        flip_button.pack(fill="x", pady=(0, 8))

        self.theme_button = tk.Button(self.fen_frame, text="Toggle Dark / Light Theme", command=self._toggle_theme)
        self.theme_button.pack(fill="x")

        self.analysis_frame = tk.LabelFrame(self.controls_frame, text="Analysis", padx=10, pady=10)
        self.analysis_frame.pack(pady=10, padx=10, fill="x")

        self.analyze_button = tk.Button(
            self.analysis_frame, text="Analyze Position", command=self._start_analysis, state=tk.DISABLED
        )
        self.analyze_button.pack(fill="x", pady=5)

        tk.Label(self.analysis_frame, text="Current Player:").pack(anchor="w")
        self.player_label = tk.Label(self.analysis_frame, text="", font=("TkDefaultFont", 10, "bold"))
        self.player_label.pack(anchor="w", pady=(0, 5))

        tk.Label(self.analysis_frame, text="Best Move:").pack(anchor="w")
        self.best_move_label = tk.Label(self.analysis_frame, text="", font=("TkDefaultFont", 12, "bold"))
        self.best_move_label.pack(anchor="w", pady=(0, 5))

        tk.Label(self.analysis_frame, text="Evaluation:").pack(anchor="w")
        self.evaluation_label = tk.Label(self.analysis_frame, text="", font=("TkDefaultFont", 12, "bold"))
        self.evaluation_label.pack(anchor="w", pady=(0, 5))

        self.status_label = tk.Label(
            self.controls_frame, text="Ready. Provide Stockfish path (or 'stockfish').", wraplength=380, justify="left"
        )
        self.status_label.pack(pady=10, fill="x")

        detected = self._find_stockfish_in_path()
        if detected:
            self.stockfish_path_var.set(detected)
            self._set_status("Detected Stockfish in PATH. Click 'Connect to Stockfish'.", "info")
        else:
            self._set_status("Ready. Provide Stockfish path (or 'stockfish').", "info")

    # ----------------------------
    # Board rendering
    # ----------------------------
    def _draw_board(self):
        self.canvas.delete("all")
        p = self._palette()

        coord_offset = 30
        for i in range(8):
            for j in range(8):
                x1, y1 = j * self.square_size + coord_offset, i * self.square_size + coord_offset
                x2, y2 = x1 + self.square_size, y1 + self.square_size
                color = p["board_light"] if (i + j) % 2 == 0 else p["board_dark"]
                self.canvas.create_rectangle(x1, y1, x2, y2, fill=color, tags="square", outline="")

        self._draw_pieces(coord_offset)
        self._draw_coordinates(coord_offset)
        self._update_player_label()

    def _draw_pieces(self, offset: int):
        self.canvas.delete("piece")
        for square in chess.SQUARES:
            piece = self.board.piece_at(square)
            if not piece:
                continue

            x, y = self._square_to_pixel(square, offset)
            piece_symbol = piece.unicode_symbol()
            fill_color = "#101010" if piece.color == chess.BLACK else "#f0f0f0"

            self.canvas.create_text(
                x,
                y,
                text=piece_symbol,
                font=(self.piece_font_family, self.square_size // 2, "bold"),
                tags="piece",
                fill=fill_color,
            )

    def _draw_coordinates(self, offset: int):
        p = self._palette()
        for i in range(8):
            rank_label = str(8 - i) if not self.board_flipped else str(i + 1)
            self.canvas.create_text(
                offset / 2,
                i * self.square_size + offset + self.square_size / 2,
                text=rank_label,
                font=("TkDefaultFont", 10),
                fill=p["coord_fg"],
                tags="coordinate",
            )
            self.canvas.create_text(
                8 * self.square_size + offset + offset / 2,
                i * self.square_size + offset + self.square_size / 2,
                text=rank_label,
                font=("TkDefaultFont", 10),
                fill=p["coord_fg"],
                tags="coordinate",
            )

            file_label = chr(ord("a") + i) if not self.board_flipped else chr(ord("h") - i)
            self.canvas.create_text(
                i * self.square_size + offset + self.square_size / 2,
                offset / 2,
                text=file_label,
                font=("TkDefaultFont", 10),
                fill=p["coord_fg"],
                tags="coordinate",
            )
            self.canvas.create_text(
                i * self.square_size + offset + self.square_size / 2,
                8 * self.square_size + offset + offset / 2,
                text=file_label,
                font=("TkDefaultFont", 10),
                fill=p["coord_fg"],
                tags="coordinate",
            )

    # ----------------------------
    # Interaction
    # ----------------------------
    def _on_square_click(self, event):
        coord_offset = 30

        click_x = event.x - coord_offset
        click_y = event.y - coord_offset

        file = click_x // self.square_size
        if self.board_flipped:
            rank = click_y // self.square_size
        else:
            rank = 7 - (click_y // self.square_size)

        if not (0 <= file < 8 and 0 <= rank < 8):
            return

        clicked_square = chess.square(file, rank)

        if self.selected_square is not None:
            move = chess.Move(self.selected_square, clicked_square)

            piece = self.board.piece_at(self.selected_square)
            if piece and piece.piece_type == chess.PAWN:
                if (self.board.turn == chess.WHITE and chess.square_rank(clicked_square) == 7) or (
                    self.board.turn == chess.BLACK and chess.square_rank(clicked_square) == 0
                ):
                    move.promotion = chess.QUEEN

            if move in self.board.legal_moves:
                self.board.push(move)
                self.fen_var.set(self.board.fen())
                self.selected_square = None
                self._draw_board()
                self._clear_highlights()
            else:
                self.selected_square = None
                self._clear_highlights()
                piece2 = self.board.piece_at(clicked_square)
                if piece2 and piece2.color == self.board.turn:
                    self.selected_square = clicked_square
                    self._highlight_legal_moves(clicked_square)

        else:
            piece = self.board.piece_at(clicked_square)
            if piece and piece.color == self.board.turn:
                self.selected_square = clicked_square
                self._highlight_legal_moves(clicked_square)

    def _highlight_legal_moves(self, square):
        self._clear_highlights()
        coord_offset = 30
        p = self._palette()
        accent = p["accent"]

        x, y = self._square_to_pixel_coords(square, coord_offset)
        self.canvas.create_rectangle(
            x, y, x + self.square_size, y + self.square_size, outline=accent, width=3, tags="highlight"
        )

        for move in self.board.legal_moves:
            if move.from_square == square:
                dest_square = move.to_square
                x, y = self._square_to_pixel_coords(dest_square, coord_offset)
                self.canvas.create_oval(
                    x + self.square_size * 0.3,
                    y + self.square_size * 0.3,
                    x + self.square_size * 0.7,
                    y + self.square_size * 0.7,
                    fill=accent,
                    outline="",
                    tags="highlight",
                )

    def _clear_highlights(self):
        self.canvas.delete("highlight")
        self.legal_moves_highlight = []

    def _flip_board(self):
        self.board_flipped = not self.board_flipped
        self.selected_square = None
        self._draw_board()
        self._clear_highlights()

    def _reset_board_from_fen(self):
        fen = self.fen_var.get()
        try:
            self.board.set_fen(fen)
            self._draw_board()
            self._set_status("Board reset from FEN.", "info")
        except ValueError:
            messagebox.showerror("Invalid FEN", "The FEN string is invalid.")

    def _update_player_label(self):
        player_turn = "White" if self.board.turn == chess.WHITE else "Black"
        self.player_label.config(text=player_turn)

    def _square_to_pixel(self, square, offset):
        x, y_topleft = self._square_to_pixel_coords(square, offset)
        return x + self.square_size / 2, y_topleft + self.square_size / 2

    def _square_to_pixel_coords(self, square, offset):
        file = chess.square_file(square)
        rank = chess.square_rank(square)

        x = file * self.square_size + offset
        if self.board_flipped:
            y = rank * self.square_size + offset
        else:
            y = (7 - rank) * self.square_size + offset

        return x, y

    # ----------------------------
    # Engine threading and analysis
    # ----------------------------
    def _start_engine_thread(self):
        self.engine_thread = threading.Thread(target=self._engine_worker_loop, daemon=True)
        self.engine_thread.start()

    def _engine_worker_loop(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self._async_engine_handler())
        loop.close()

    async def _async_engine_handler(self):
        while True:
            try:
                command, data = self.request_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            if command == "connect":
                sf_path = data
                if self.engine:
                    try:
                        await self.engine.quit()
                    except Exception:
                        pass
                    self.engine = None

                try:
                    _transport, self.engine = await chess.engine.popen_uci(sf_path)
                    await self.engine.ping()
                    self.result_queue.put(("connect_success", None))
                except Exception as e:
                    self.engine = None
                    self.result_queue.put(("connect_fail", str(e)))

            elif command == "analyze":
                if not self.engine:
                    self.result_queue.put(("error", "Engine is not connected."))
                    continue

                board_to_analyze, time_limit = data
                try:
                    info = await self.engine.analyse(board_to_analyze, chess.engine.Limit(time=time_limit))
                    pv = info.get("pv") or []
                    analysis_result = {
                        "move": pv[0].uci() if pv else "N/A",
                        "score": info.get("score"),
                        "turn": board_to_analyze.turn,
                    }
                    self.result_queue.put(("analysis_result", analysis_result))
                except Exception as e:
                    self.result_queue.put(("error", f"Analysis failed: {e}"))

            elif command == "quit":
                if self.engine:
                    try:
                        await self.engine.quit()
                    except Exception:
                        pass
                break

    def _check_result_queue(self):
        try:
            msg_type, data = self.result_queue.get_nowait()
            p = self._palette()

            if msg_type == "connect_success":
                self.sf_status_label.config(text="Status: Connected!", fg=p["success"])
                self.analyze_button.config(state=tk.NORMAL)
                self._set_status("Stockfish connected. Ready to analyze.", "success")

            elif msg_type == "connect_fail":
                self.sf_status_label.config(text="Status: Connection failed", fg=p["error"])
                self.analyze_button.config(state=tk.DISABLED)
                self._set_status("Connection failed.", "error")
                messagebox.showerror("Connection Error", f"Could not connect to Stockfish:\n{data}")

            elif msg_type == "analysis_result":
                self._update_gui_with_analysis(data)
                self._set_status("Analysis complete.", "success")
                self.analyze_button.config(state=tk.NORMAL)

            elif msg_type == "error":
                messagebox.showerror("Error", data)
                self._set_status(f"Error: {data}", "error")
                self.analyze_button.config(state=tk.NORMAL)

        except queue.Empty:
            pass

        self.master.after(100, self._check_result_queue)

    # ----------------------------
    # Stockfish plumbing
    # ----------------------------
    def _browse_stockfish(self):
        if sys.platform.startswith("win"):
            filetypes = [("Executable files", "*.exe"), ("All files", "*.*")]
        else:
            filetypes = [("All files", "*")]

        filename = filedialog.askopenfilename(title="Select Stockfish Executable", filetypes=filetypes)
        if filename:
            self.stockfish_path_var.set(filename)

    def _connect_to_stockfish(self):
        user_value = self.stockfish_path_var.get().strip()
        resolved = self._resolve_engine_path(user_value)

        if not resolved:
            messagebox.showerror(
                "Error",
                "Invalid Stockfish executable.\n\n"
                "On Linux you can usually enter 'stockfish' (if installed) or browse to the binary.\n"
                "If you selected a file, ensure it is executable.",
            )
            return

        self.request_queue.put(("connect", resolved))
        self._set_status("Attempting to connect to Stockfish...", "warning")

    def _start_analysis(self):
        self._set_status("Analyzing position...", "warning")
        self.analyze_button.config(state=tk.DISABLED)
        self.best_move_label.config(text="...")
        self.evaluation_label.config(text="...")

        self.request_queue.put(("analyze", (self.board.copy(), 2.0)))

    def _update_gui_with_analysis(self, result: dict):
        p = self._palette()
        best_move_uci = result.get("move")
        score_obj = result.get("score")
        analyzed_turn = result.get("turn", self.board.turn)

        self.best_move_label.config(text=best_move_uci or "N/A", fg=p["text"])

        if score_obj is None:
            self.evaluation_label.config(text="(Not available)", fg=p["muted"])
            return

        pov_score = score_obj.pov(analyzed_turn)

        if pov_score.is_mate():
            mate_moves = pov_score.mate()
            if mate_moves is None:
                self.evaluation_label.config(text="Mate", fg=p["text"])
            elif mate_moves > 0:
                self.evaluation_label.config(text=f"Mate in {mate_moves}", fg=p["success"])
            else:
                self.evaluation_label.config(text=f"Mated in {-mate_moves}", fg=p["error"])
        else:
            cp_score = pov_score.score(mate_score=10000)
            if cp_score is None:
                self.evaluation_label.config(text="0.00", fg=p["text"])
                return
            eval_str = f"{cp_score / 100:.2f}"
            if cp_score > 50:
                self.evaluation_label.config(text=eval_str, fg=p["success"])
            elif cp_score < -50:
                self.evaluation_label.config(text=eval_str, fg=p["error"])
            else:
                self.evaluation_label.config(text=eval_str, fg=p["text"])

    # ----------------------------
    # Shutdown
    # ----------------------------
    def _on_closing(self):
        try:
            self.request_queue.put(("quit", None))
        except Exception:
            pass

        if self.engine_thread and self.engine_thread.is_alive():
            self.engine_thread.join(timeout=2.0)

        self.master.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = ChessAnalyzerApp(root)
    root.mainloop()
