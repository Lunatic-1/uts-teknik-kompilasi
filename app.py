import re
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
from dataclasses import dataclass
from typing import List, Optional, Tuple

@dataclass
class Token:
    jenis: str
    nilai: str
    baris: int

@dataclass
class SymbolEntry:
    nama: str
    tipe: str
    nilai: Optional[str] = None

@dataclass
class TACInstruction:
    op: str
    arg1: str = ""
    arg2: str = ""
    result: str = ""

    def __str__(self):
        if self.op == "=":
            return f"{self.result} = {self.arg1}"
        elif self.op in ("+", "-", "*", "/"):
            return f"{self.result} = {self.arg1} {self.op} {self.arg2}"
        elif self.op == "PARAM":
            return f"param {self.arg1}"
        elif self.op == "CALL":
            return f"call {self.arg1}, {self.arg2}"
        elif self.op == "LABEL":
            return f"{self.arg1}:"
        elif self.op == "PRINT":
            return f"call print, {self.arg1}"
        else:
            return f"{self.op} {self.arg1} {self.arg2} {self.result}".strip()

KEYWORDS = {"int", "float", "string", "print", "if", "else", "while", "for", "return"}

TOKEN_PATTERN = re.compile(
    r"(?P<COMMENT>//.*)"
    r"|(?P<STRING>\"[^\"]*\")"
    r"|(?P<FLOAT_NUM>\d+\.\d+)"
    r"|(?P<NUMBER>\d+)"
    r"|(?P<IDENT>[A-Za-z_]\w*)"
    r"|(?P<OP>[+\-*/=])"
    r"|(?P<RELOP>[<>!]=?|==)"
    r"|(?P<PUNCT>[();{},])"
    r"|(?P<SKIP>[ \t]+)"
    r"|(?P<NEWLINE>\n)"
    r"|(?P<MISMATCH>.)"
)

def lexical_analysis(source_code: str) -> Tuple[List[Token], List[str]]:
    tokens: List[Token] = []
    errors: List[str] = []
    baris = 1

    for match in TOKEN_PATTERN.finditer(source_code):
        jenis = match.lastgroup
        nilai = match.group()

        if jenis == "NEWLINE":
            baris += 1
            continue
        elif jenis in ("SKIP", "COMMENT"):
            continue
        elif jenis == "MISMATCH":
            errors.append(f"[Lexer] Baris {baris}: Karakter tidak dikenal '{nilai}'")
            continue

        if jenis == "IDENT" and nilai in KEYWORDS:
            jenis = "KEYWORD"
        elif jenis == "FLOAT_NUM":
            jenis = "FLOAT_LIT"
        elif jenis == "NUMBER":
            jenis = "INT_LIT"
        elif jenis == "STRING":
            jenis = "STRING_LIT"

        tokens.append(Token(jenis=jenis, nilai=nilai, baris=baris))

    return tokens, errors

class Parser:
    def __init__(self, tokens: List[Token]):
        self.tokens = tokens
        self.pos = 0
        self.errors: List[str] = []
        self.ast: List[dict] = []

    def current(self) -> Optional[Token]:
        if self.pos < len(self.tokens):
            return self.tokens[self.pos]
        return None

    def peek(self) -> Optional[Token]:
        return self.current()

    def advance(self) -> Token:
        tok = self.tokens[self.pos]
        self.pos += 1
        return tok

    def expect(self, jenis: str, nilai: str = None) -> Optional[Token]:
        tok = self.current()
        if tok is None:
            self.errors.append(f"[Parser] Akhir kode tiba-tiba, diharapkan '{nilai or jenis}'")
            return None
        if tok.jenis != jenis or (nilai and tok.nilai != nilai):
            self.errors.append(
                f"[Parser] Baris {tok.baris}: Diharapkan '{nilai or jenis}', "
                f"ditemukan '{tok.nilai}'"
            )
            return None
        return self.advance()

    def parse(self) -> List[dict]:
        while self.current() is not None:
            stmt = self.parse_statement()
            if stmt:
                self.ast.append(stmt)
            else:
                if self.current():
                    self.advance()
        return self.ast

    def parse_statement(self) -> Optional[dict]:
        tok = self.current()
        if tok is None:
            return None

        if tok.jenis == "KEYWORD" and tok.nilai in ("int", "float", "string"):
            return self.parse_declaration()
        elif tok.jenis == "KEYWORD" and tok.nilai == "print":
            return self.parse_print()
        elif tok.jenis == "IDENT":
            return self.parse_assignment()
        else:
            self.errors.append(
                f"[Parser] Baris {tok.baris}: Statement tidak valid, "
                f"ditemukan '{tok.nilai}'"
            )
            return None

    def parse_declaration(self) -> Optional[dict]:
        tipe_tok = self.advance()
        nama_tok = self.expect("IDENT")
        if not nama_tok:
            return None
        eq_tok = self.expect("OP", "=")
        if not eq_tok:
            return None
        expr = self.parse_expression()
        if expr is None:
            return None
        self.expect("PUNCT", ";")
        return {
            "type": "DECLARATION",
            "data_type": tipe_tok.nilai,
            "name": nama_tok.nilai,
            "value": expr,
            "line": tipe_tok.baris,
        }

    def parse_assignment(self) -> Optional[dict]:
        nama_tok = self.advance()
        eq_tok = self.expect("OP", "=")
        if not eq_tok:
            return None
        expr = self.parse_expression()
        if expr is None:
            return None
        self.expect("PUNCT", ";")
        return {
            "type": "ASSIGNMENT",
            "name": nama_tok.nilai,
            "value": expr,
            "line": nama_tok.baris,
        }

    def parse_print(self) -> Optional[dict]:
        print_tok = self.advance()
        self.expect("PUNCT", "(")
        expr = self.parse_expression()
        if expr is None:
            return None
        self.expect("PUNCT", ")")
        self.expect("PUNCT", ";")
        return {
            "type": "PRINT",
            "value": expr,
            "line": print_tok.baris,
        }

    def parse_expression(self) -> Optional[dict]:
        left = self.parse_term()
        if left is None:
            return None

        while (self.current() and self.current().jenis == "OP"
               and self.current().nilai in ("+", "-")):
            op = self.advance()
            right = self.parse_term()
            if right is None:
                return None
            left = {
                "type": "BINOP",
                "op": op.nilai,
                "left": left,
                "right": right,
                "line": op.baris,
            }
        return left

    def parse_term(self) -> Optional[dict]:
        left = self.parse_factor()
        if left is None:
            return None

        while (self.current() and self.current().jenis == "OP"
               and self.current().nilai in ("*", "/")):
            op = self.advance()
            right = self.parse_factor()
            if right is None:
                return None
            left = {
                "type": "BINOP",
                "op": op.nilai,
                "left": left,
                "right": right,
                "line": op.baris,
            }
        return left

    def parse_factor(self) -> Optional[dict]:
        tok = self.current()
        if tok is None:
            self.errors.append("[Parser] Ekspresi tidak lengkap di akhir kode")
            return None

        if tok.jenis == "INT_LIT":
            self.advance()
            return {"type": "LITERAL", "data_type": "int", "value": tok.nilai, "line": tok.baris}
        elif tok.jenis == "FLOAT_LIT":
            self.advance()
            return {"type": "LITERAL", "data_type": "float", "value": tok.nilai, "line": tok.baris}
        elif tok.jenis == "STRING_LIT":
            self.advance()
            return {"type": "LITERAL", "data_type": "string", "value": tok.nilai, "line": tok.baris}
        elif tok.jenis == "IDENT":
            self.advance()
            return {"type": "IDENTIFIER", "name": tok.nilai, "line": tok.baris}
        elif tok.jenis == "PUNCT" and tok.nilai == "(":
            self.advance()
            expr = self.parse_expression()
            self.expect("PUNCT", ")")
            return expr
        else:
            self.errors.append(
                f"[Parser] Baris {tok.baris}: Faktor tidak valid '{tok.nilai}'"
            )
            return None

class SemanticAnalyzer:
    def __init__(self):
        self.symbol_table: dict[str, SymbolEntry] = {}
        self.errors: List[str] = []
        self.warnings: List[str] = []

    def analyze(self, ast: List[dict]):
        for node in ast:
            self._analyze_node(node)

    def _analyze_node(self, node: dict):
        ntype = node["type"]
        if ntype == "DECLARATION":
            self._analyze_declaration(node)
        elif ntype == "ASSIGNMENT":
            self._analyze_assignment(node)
        elif ntype == "PRINT":
            self._analyze_print(node)

    def _analyze_declaration(self, node: dict):
        name = node["name"]
        dtype = node["data_type"]
        line = node["line"]

        if name in self.symbol_table:
            self.errors.append(
                f"[Semantik] Baris {line}: Variabel '{name}' sudah dideklarasikan sebelumnya"
            )
            return

        expr_type = self._get_expr_type(node["value"])
        if expr_type and expr_type != dtype:
            if dtype == "float" and expr_type == "int":
                self.warnings.append(
                    f"[Semantik] Baris {line}: Konversi implisit int → float untuk '{name}'"
                )
            elif dtype == "int" and expr_type == "float":
                self.warnings.append(
                    f"[Semantik] Baris {line}: Konversi float → int, kemungkinan kehilangan presisi untuk '{name}'"
                )
            elif (dtype in ("int", "float") and expr_type == "string") or \
                 (dtype == "string" and expr_type in ("int", "float")):
                self.errors.append(
                    f"[Semantik] Baris {line}: Tipe tidak cocok, "
                    f"variabel '{name}' bertipe '{dtype}' "
                    f"tetapi nilai bertipe '{expr_type}'"
                )
                return

        self.symbol_table[name] = SymbolEntry(nama=name, tipe=dtype, nilai=str(node["value"]))

    def _analyze_assignment(self, node: dict):
        name = node["name"]
        line = node["line"]

        if name not in self.symbol_table:
            self.errors.append(
                f"[Semantik] Baris {line}: Variabel '{name}' belum dideklarasikan"
            )
            return

        entry = self.symbol_table[name]
        expr_type = self._get_expr_type(node["value"])
        if expr_type and expr_type != entry.tipe:
            if entry.tipe == "float" and expr_type == "int":
                self.warnings.append(
                    f"[Semantik] Baris {line}: Konversi implisit int → float untuk '{name}'"
                )
            elif entry.tipe == "int" and expr_type == "float":
                self.warnings.append(
                    f"[Semantik] Baris {line}: Konversi float → int untuk '{name}'"
                )
            elif (entry.tipe in ("int", "float") and expr_type == "string") or \
                 (entry.tipe == "string" and expr_type in ("int", "float")):
                self.errors.append(
                    f"[Semantik] Baris {line}: Tipe tidak cocok saat assignment '{name}', "
                    f"diharapkan '{entry.tipe}' tetapi ditemukan '{expr_type}'"
                )

    def _analyze_print(self, node: dict):
        self._get_expr_type(node["value"])

    def _get_expr_type(self, expr: dict) -> Optional[str]:
        if expr is None:
            return None
        etype = expr["type"]
        if etype == "LITERAL":
            return expr["data_type"]
        elif etype == "IDENTIFIER":
            name = expr["name"]
            if name not in self.symbol_table:
                self.errors.append(
                    f"[Semantik] Baris {expr['line']}: Variabel '{name}' belum dideklarasikan"
                )
                return None
            return self.symbol_table[name].tipe
        elif etype == "BINOP":
            left_type = self._get_expr_type(expr["left"])
            right_type = self._get_expr_type(expr["right"])
            if left_type == "string" or right_type == "string":
                if expr["op"] == "+":
                    return "string"
                else:
                    line = expr.get("line", "?")
                    self.errors.append(
                        f"[Semantik] Baris {line}: Operator '{expr['op']}' "
                        f"tidak dapat digunakan pada string"
                    )
                    return None
            if left_type == "float" or right_type == "float":
                return "float"
            return "int"
        return None

class IntermediateCodeGenerator:
    def __init__(self):
        self.instructions: List[TACInstruction] = []
        self.temp_count = 0

    def new_temp(self) -> str:
        self.temp_count += 1
        return f"t{self.temp_count}"

    def generate(self, ast: List[dict]):
        for node in ast:
            self._gen_statement(node)

    def _gen_statement(self, node: dict):
        ntype = node["type"]
        if ntype == "DECLARATION":
            result = self._gen_expression(node["value"])
            self.instructions.append(TACInstruction(op="=", arg1=result, result=node["name"]))
        elif ntype == "ASSIGNMENT":
            result = self._gen_expression(node["value"])
            self.instructions.append(TACInstruction(op="=", arg1=result, result=node["name"]))
        elif ntype == "PRINT":
            result = self._gen_expression(node["value"])
            self.instructions.append(TACInstruction(op="PRINT", arg1=result))

    def _gen_expression(self, expr: dict) -> str:
        etype = expr["type"]
        if etype == "LITERAL":
            return expr["value"]
        elif etype == "IDENTIFIER":
            return expr["name"]
        elif etype == "BINOP":
            left = self._gen_expression(expr["left"])
            right = self._gen_expression(expr["right"])
            temp = self.new_temp()
            self.instructions.append(
                TACInstruction(op=expr["op"], arg1=left, arg2=right, result=temp)
            )
            return temp
        return "?"

class CodeOptimizer:
    def __init__(self):
        self.log: List[str] = []

    def optimize(self, instructions: List[TACInstruction]) -> List[TACInstruction]:
        optimized = list(instructions)
        optimized = self._constant_folding(optimized)
        optimized = self._constant_propagation(optimized)
        optimized = self._dead_code_elimination(optimized)
        optimized = self._strength_reduction(optimized)
        if not self.log:
            self.log.append("Tidak ada optimasi yang dapat dilakukan.")
        return optimized

    def _constant_folding(self, instructions: List[TACInstruction]) -> List[TACInstruction]:
        result = []
        for instr in instructions:
            if instr.op in ("+", "-", "*", "/"):
                try:
                    a = self._try_numeric(instr.arg1)
                    b = self._try_numeric(instr.arg2)
                    if a is not None and b is not None:
                        if instr.op == "+":
                            val = a + b
                        elif instr.op == "-":
                            val = a - b
                        elif instr.op == "*":
                            val = a * b
                        elif instr.op == "/":
                            val = a / b if b != 0 else None
                        else:
                            val = None
                        if val is not None:
                            val_str = str(int(val)) if val == int(val) else str(val)
                            self.log.append(
                                f"Constant Folding: {instr} → {instr.result} = {val_str}"
                            )
                            result.append(TACInstruction(op="=", arg1=val_str, result=instr.result))
                            continue
                except (ValueError, ZeroDivisionError):
                    pass
            result.append(instr)
        return result

    def _constant_propagation(self, instructions: List[TACInstruction]) -> List[TACInstruction]:
        constants = {}
        result = []
        for instr in instructions:
            if instr.op == "=" and self._try_numeric(instr.arg1) is not None:
                constants[instr.result] = instr.arg1

            new_instr = TACInstruction(op=instr.op, arg1=instr.arg1,
                                       arg2=instr.arg2, result=instr.result)

            changed = False
            if new_instr.arg1 in constants and new_instr.op != "=":
                old = new_instr.arg1
                new_instr.arg1 = constants[new_instr.arg1]
                changed = True
            if new_instr.arg2 in constants:
                old = new_instr.arg2
                new_instr.arg2 = constants[new_instr.arg2]
                changed = True

            if changed:
                self.log.append(f"Constant Propagation: substitusi dilakukan pada {instr.result}")

            result.append(new_instr)
        return result

    def _dead_code_elimination(self, instructions: List[TACInstruction]) -> List[TACInstruction]:
        used = set()
        for instr in instructions:
            if instr.op == "PRINT":
                used.add(instr.arg1)
            else:
                if instr.arg1 and not self._is_literal(instr.arg1):
                    used.add(instr.arg1)
                if instr.arg2 and not self._is_literal(instr.arg2):
                    used.add(instr.arg2)

        result = []
        for instr in instructions:
            if (instr.result.startswith("t") and instr.result not in used
                    and instr.op != "PRINT"):
                self.log.append(f"Dead Code Elimination: {instr} dihapus")
                continue
            result.append(instr)
        return result

    def _strength_reduction(self, instructions: List[TACInstruction]) -> List[TACInstruction]:
        result = []
        for instr in instructions:
            if instr.op == "*":
                if instr.arg2 == "2":
                    self.log.append(
                        f"Strength Reduction: {instr.arg1} * 2 → {instr.arg1} + {instr.arg1}"
                    )
                    result.append(TACInstruction(
                        op="+", arg1=instr.arg1, arg2=instr.arg1, result=instr.result
                    ))
                    continue
                elif instr.arg1 == "2":
                    self.log.append(
                        f"Strength Reduction: 2 * {instr.arg2} → {instr.arg2} + {instr.arg2}"
                    )
                    result.append(TACInstruction(
                        op="+", arg1=instr.arg2, arg2=instr.arg2, result=instr.result
                    ))
                    continue
            result.append(instr)
        return result

    @staticmethod
    def _try_numeric(s: str):
        try:
            if "." in s:
                return float(s)
            return int(s)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _is_literal(s: str) -> bool:
        if not s:
            return False
        try:
            float(s)
            return True
        except ValueError:
            return s.startswith('"') and s.endswith('"')

class TargetCodeGenerator:
    def __init__(self):
        self.code: List[str] = []

    def generate(self, instructions: List[TACInstruction]) -> List[str]:
        self.code.append("; === TARGET CODE (Pseudo-Assembly) ===")
        self.code.append("; Generated by Laboratorium Teknik Kompilasi")
        self.code.append("SECTION .text")
        self.code.append("  global _start")
        self.code.append("_start:")

        for instr in instructions:
            self.code.append(f"  ; TAC: {instr}")
            if instr.op == "=":
                self.code.append(f"  MOV  {instr.result}, {instr.arg1}")
            elif instr.op in ("+", "-", "*", "/"):
                self.code.append(f"  MOV  R0, {instr.arg1}")
                op_map = {"+": "ADD", "-": "SUB", "*": "MUL", "/": "DIV"}
                self.code.append(f"  {op_map[instr.op]}  R0, {instr.arg2}")
                self.code.append(f"  MOV  {instr.result}, R0")
            elif instr.op == "PRINT":
                self.code.append(f"  PUSH {instr.arg1}")
                self.code.append(f"  CALL _print")
            self.code.append("")

        self.code.append("  ; Exit program")
        self.code.append("  MOV  R0, 0")
        self.code.append("  CALL _exit")
        self.code.append("SECTION .data")

        return self.code

class Compiler:
    def compile(self, source: str) -> dict:
        result = {
            "success": True,
            "tokens": [],
            "token_errors": [],
            "ast": [],
            "parse_errors": [],
            "semantic_errors": [],
            "semantic_warnings": [],
            "symbol_table": {},
            "tac_before": [],
            "tac_after": [],
            "optimization_log": [],
            "target_code": [],
        }

        tokens, lex_errors = lexical_analysis(source)
        result["tokens"] = tokens
        result["token_errors"] = lex_errors
        if lex_errors:
            result["success"] = False

        parser = Parser(tokens)
        ast = parser.parse()
        result["ast"] = ast
        result["parse_errors"] = parser.errors
        if parser.errors:
            result["success"] = False

        sem = SemanticAnalyzer()
        sem.analyze(ast)
        result["semantic_errors"] = sem.errors
        result["semantic_warnings"] = sem.warnings
        result["symbol_table"] = sem.symbol_table
        if sem.errors:
            result["success"] = False

        icg = IntermediateCodeGenerator()
        icg.generate(ast)
        result["tac_before"] = list(icg.instructions)

        optimizer = CodeOptimizer()
        optimized = optimizer.optimize(icg.instructions)
        result["tac_after"] = optimized
        result["optimization_log"] = optimizer.log

        tcg = TargetCodeGenerator()
        result["target_code"] = tcg.generate(optimized)

        return result

CONTOH_KODE = [
    (
        "Aritmetika Dasar",
        """\
int a = 10;
int b = 20;
int c = a + b;
print(c);"""
    ),
    (
        "Operasi Float",
        """\
float x = 3.14;
float y = 2.0;
float z = x * y;
print(z);"""
    ),
    (
        "String & Multi-Var",
        """\
string nama = "Teknik Kompilasi";
int nilai = 100;
print(nama);
print(nilai);"""
    ),
    (
        "Ekspresi Kompleks",
        """\
int a = 5;
int b = 3;
int c = a * 2 + b;
int d = c - a;
print(d);"""
    ),
    (
        "Reassignment",
        """\
int x = 10;
int y = 20;
x = x + y;
y = x * 2;
print(x);
print(y);"""
    ),
    (
        "Constant Folding",
        """\
int a = 3 + 4;
int b = a * 2;
int c = 10 / 2;
print(b);
print(c);"""
    ),
    (
        "Error: Var Belum Deklarasi",
        """\
int a = 10;
b = a + 5;
print(b);"""
    ),
    (
        "Error: Tipe Tidak Cocok",
        """\
int x = "hello";
print(x);"""
    ),
]

class App(tk.Tk):
    BG          = "#1e1e2e"
    BG_DARK     = "#181825"
    BG_INPUT    = "#11111b"
    FG          = "#cdd6f4"
    FG_DIM      = "#a6adc8"
    ACCENT      = "#89b4fa"
    ACCENT2     = "#a6e3a1"
    RED         = "#f38ba8"
    YELLOW      = "#f9e2af"
    GREEN       = "#a6e3a1"
    MAUVE       = "#cba6f7"
    TEAL        = "#94e2d5"
    PEACH       = "#fab387"
    BTN_BG      = "#313244"
    BTN_HOVER   = "#45475a"

    def __init__(self):
        super().__init__()
        self.title("Laboratorium Teknik Kompilasi — Python")
        self.geometry("1200x750")
        self.minsize(1000, 600)
        self.configure(bg=self.BG)
        self.compiler = Compiler()
        self._build_ui()
        self._show_welcome()

    def _build_ui(self):
        header = tk.Frame(self, bg=self.BG_DARK, pady=10)
        header.pack(fill="x")
        tk.Label(
            header,
            text="LABORATORIUM TEKNIK KOMPILASI",
            font=("Segoe UI", 20, "bold"),
            fg=self.ACCENT,
            bg=self.BG_DARK,
        ).pack()
        tk.Label(
            header,
            text="Lexer  •  Parser  •  Semantik  •  Kode Antara  •  Optimasi  •  Kode Target",
            font=("Segoe UI", 10),
            fg=self.FG_DIM,
            bg=self.BG_DARK,
        ).pack()

        body = tk.PanedWindow(
            self, orient="horizontal", bg=self.BG,
            sashwidth=6, sashrelief="flat",
        )
        body.pack(fill="both", expand=True, padx=8, pady=(4, 0))

        left = tk.Frame(body, bg=self.BG)
        body.add(left, width=450, minsize=300)

        tk.Label(
            left, text="Kode Sumber (bahasa mini)",
            font=("Segoe UI", 10, "bold"), fg=self.TEAL, bg=self.BG, anchor="w",
        ).pack(fill="x", pady=(4, 2))

        self.editor = scrolledtext.ScrolledText(
            left, wrap="none", font=("Consolas", 12),
            bg=self.BG_INPUT, fg=self.FG, insertbackground=self.ACCENT,
            selectbackground=self.ACCENT, selectforeground=self.BG_INPUT,
            relief="flat", bd=0, padx=8, pady=8,
        )
        self.editor.pack(fill="both", expand=True)

        self.editor.bind("<KeyRelease>", self._on_editor_change)

        right = tk.Frame(body, bg=self.BG)
        body.add(right, minsize=400)

        self.notebook = ttk.Notebook(right)
        self._configure_notebook_style()
        self.notebook.pack(fill="both", expand=True, pady=(4, 0))

        tab_defs = [
            ("Ringkasan",       "tab_summary"),
            ("1. Token / Lexer","tab_tokens"),
            ("2. Parser & Sem", "tab_parser"),
            ("3. Kode Antara",  "tab_tac"),
            ("4. Optimasi",     "tab_opt"),
            ("5. Kode Target",  "tab_target"),
        ]
        for label, attr in tab_defs:
            frame = tk.Frame(self.notebook, bg=self.BG_INPUT)
            text_widget = scrolledtext.ScrolledText(
                frame, wrap="word", font=("Consolas", 11),
                bg=self.BG_INPUT, fg=self.FG,
                relief="flat", bd=0, padx=10, pady=8,
                state="disabled",
            )
            text_widget.pack(fill="both", expand=True)
            self.notebook.add(frame, text=label)
            setattr(self, attr, text_widget)

        btn_bar = tk.Frame(self, bg=self.BG, pady=8)
        btn_bar.pack(fill="x", padx=8)

        for text, cmd, color in [
            ("▶  Kompilasi", self._do_compile, self.ACCENT),
            ("📋  Contoh",   self._do_contoh,  self.PEACH),
            ("🗑  Bersih",   self._do_clear,   self.RED),
        ]:
            btn = tk.Button(
                btn_bar, text=text, command=cmd,
                font=("Segoe UI", 11, "bold"),
                bg=self.BTN_BG, fg=color,
                activebackground=self.BTN_HOVER, activeforeground=color,
                relief="flat", padx=18, pady=6, cursor="hand2",
                bd=0,
            )
            btn.pack(side="left", padx=(0, 10))

        self.status_var = tk.StringVar(
            value="Sintaks: int/float/string, assignment (=), aritmetika (+,-,*,/), "
                  "print(), kurung, titik-koma (;)"
        )
        status = tk.Label(
            self, textvariable=self.status_var,
            font=("Segoe UI", 9), fg=self.FG_DIM, bg=self.BG_DARK,
            anchor="w", padx=10, pady=4,
        )
        status.pack(fill="x", side="bottom")

    def _configure_notebook_style(self):
        style = ttk.Style()
        style.theme_use("default")
        style.configure("TNotebook", background=self.BG, borderwidth=0)
        style.configure(
            "TNotebook.Tab",
            background=self.BTN_BG, foreground=self.FG_DIM,
            padding=[12, 6], font=("Segoe UI", 9, "bold"),
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", self.BG_INPUT)],
            foreground=[("selected", self.ACCENT)],
        )

    def _set_tab_text(self, widget, text: str):
        widget.config(state="normal")
        widget.delete("1.0", "end")
        widget.insert("end", text)
        widget.config(state="disabled")

    def _on_editor_change(self, event=None):
        pass

    def _show_welcome(self):
        msg = (
            "Selamat datang di Laboratorium Teknik Kompilasi!\n"
            "═══════════════════════════════════════════════\n\n"
            "Cara penggunaan:\n"
            "  1. Tulis kode pada panel kiri, atau klik 'Contoh'\n"
            "  2. Klik 'Kompilasi' untuk menjalankan proses kompilasi\n"
            "  3. Lihat hasil pada tab-tab di panel kanan\n\n"
            "Bahasa mini yang didukung:\n"
            "  • Tipe data  : int, float, string\n"
            "  • Operator   : +, -, *, /, =\n"
            "  • Fungsi     : print(ekspresi)\n"
            "  • Komentar   : // komentar\n"
            "  • Terminator : ; (titik koma)\n\n"
            "Contoh kode:\n"
            "  int a = 10;\n"
            "  int b = 20;\n"
            "  int c = a + b;\n"
            "  print(c);\n"
        )
        self._set_tab_text(self.tab_summary, msg)

    def _do_compile(self):
        source = self.editor.get("1.0", "end").strip()
        if not source:
            messagebox.showwarning("Peringatan", "Kode sumber kosong!\nSilakan tulis kode atau klik 'Contoh'.")
            return

        result = self.compiler.compile(source)
        self._display_results(result, source)
        self.status_var.set(
            "✅ Kompilasi selesai tanpa error." if result["success"]
            else "❌ Kompilasi selesai dengan error."
        )

    def _do_contoh(self):
        menu = tk.Menu(self, tearoff=0, font=("Segoe UI", 10),
                       bg=self.BTN_BG, fg=self.FG,
                       activebackground=self.ACCENT, activeforeground=self.BG_INPUT)
        for i, (title, code) in enumerate(CONTOH_KODE):
            menu.add_command(
                label=f"  {i+1}. {title}",
                command=lambda c=code: self._load_example(c),
            )
        try:
            menu.tk_popup(
                self.winfo_pointerx(),
                self.winfo_pointery(),
            )
        finally:
            menu.grab_release()

    def _load_example(self, code: str):
        self.editor.delete("1.0", "end")
        self.editor.insert("1.0", code)
        self.status_var.set("Contoh kode dimuat. Klik 'Kompilasi' untuk menganalisis.")

    def _do_clear(self):
        self.editor.delete("1.0", "end")
        for attr in ("tab_summary", "tab_tokens", "tab_parser", "tab_tac", "tab_opt", "tab_target"):
            self._set_tab_text(getattr(self, attr), "")
        self._show_welcome()
        self.status_var.set("Editor dan hasil dibersihkan.")

    def _display_results(self, r: dict, source: str):
        lines = []
        lines.append("╔══════════════════════════════════════════╗")
        lines.append("║       RINGKASAN HASIL KOMPILASI          ║")
        lines.append("╚══════════════════════════════════════════╝\n")

        lines.append(f"Status       : {'✅ BERHASIL' if r['success'] else '❌ ADA ERROR'}")
        lines.append(f"Jumlah Token : {len(r['tokens'])}")
        lines.append(f"Jumlah AST   : {len(r['ast'])} statement")
        lines.append(f"Variabel     : {len(r['symbol_table'])}")
        lines.append(f"TAC (awal)   : {len(r['tac_before'])} instruksi")
        lines.append(f"TAC (optim)  : {len(r['tac_after'])} instruksi")
        lines.append(f"Target Code  : {len(r['target_code'])} baris\n")

        if r["token_errors"]:
            lines.append("── Error Leksikal ──")
            for e in r["token_errors"]:
                lines.append(f"  ✗ {e}")
            lines.append("")
        if r["parse_errors"]:
            lines.append("── Error Sintaks ──")
            for e in r["parse_errors"]:
                lines.append(f"  ✗ {e}")
            lines.append("")
        if r["semantic_errors"]:
            lines.append("── Error Semantik ──")
            for e in r["semantic_errors"]:
                lines.append(f"  ✗ {e}")
            lines.append("")
        if r["semantic_warnings"]:
            lines.append("── Peringatan Semantik ──")
            for e in r["semantic_warnings"]:
                lines.append(f"  ⚠ {e}")
            lines.append("")

        if r["symbol_table"]:
            lines.append("── Tabel Simbol ──")
            lines.append(f"  {'Nama':<12} {'Tipe':<10}")
            lines.append(f"  {'─'*12} {'─'*10}")
            for name, entry in r["symbol_table"].items():
                lines.append(f"  {entry.nama:<12} {entry.tipe:<10}")
            lines.append("")

        self._set_tab_text(self.tab_summary, "\n".join(lines))

        lines = []
        lines.append("╔══════════════════════════════════════════╗")
        lines.append("║       FASE 1: LEXICAL ANALYSIS           ║")
        lines.append("╚══════════════════════════════════════════╝\n")
        lines.append(f"  {'No':<5} {'Jenis':<14} {'Nilai':<20} {'Baris':<6}")
        lines.append(f"  {'─'*5} {'─'*14} {'─'*20} {'─'*6}")
        for i, tok in enumerate(r["tokens"], 1):
            lines.append(f"  {i:<5} {tok.jenis:<14} {tok.nilai:<20} {tok.baris:<6}")
        lines.append(f"\n  Total token: {len(r['tokens'])}")
        if r["token_errors"]:
            lines.append("\n  ── Error ──")
            for e in r["token_errors"]:
                lines.append(f"  ✗ {e}")
        self._set_tab_text(self.tab_tokens, "\n".join(lines))

        lines = []
        lines.append("╔══════════════════════════════════════════╗")
        lines.append("║    FASE 2: PARSING (Analisis Sintaks)     ║")
        lines.append("╚══════════════════════════════════════════╝\n")
        if r["parse_errors"]:
            for e in r["parse_errors"]:
                lines.append(f"  ✗ {e}")
        else:
            lines.append("  ✔ Sintaks valid — tidak ada error.\n")
            lines.append("  ── Abstract Syntax Tree (AST) ──")
            for i, node in enumerate(r["ast"], 1):
                lines.append(f"\n  Statement #{i}:")
                lines.extend(self._format_ast(node, indent=4))

        lines.append("\n")
        lines.append("╔══════════════════════════════════════════╗")
        lines.append("║   FASE 3: SEMANTIC ANALYSIS               ║")
        lines.append("╚══════════════════════════════════════════╝\n")
        if r["semantic_errors"]:
            for e in r["semantic_errors"]:
                lines.append(f"  ✗ {e}")
        else:
            lines.append("  ✔ Semantik valid — tidak ada error.")

        if r["semantic_warnings"]:
            lines.append("\n  ── Peringatan ──")
            for w in r["semantic_warnings"]:
                lines.append(f"  ⚠ {w}")

        if r["symbol_table"]:
            lines.append(f"\n  ── Tabel Simbol ──")
            lines.append(f"  {'Nama':<12} {'Tipe':<10}")
            lines.append(f"  {'─'*12} {'─'*10}")
            for name, entry in r["symbol_table"].items():
                lines.append(f"  {entry.nama:<12} {entry.tipe:<10}")

        self._set_tab_text(self.tab_parser, "\n".join(lines))

        lines = []
        lines.append("╔══════════════════════════════════════════╗")
        lines.append("║   FASE 4: INTERMEDIATE CODE (TAC)         ║")
        lines.append("╚══════════════════════════════════════════╝\n")
        lines.append("  Three-Address Code (sebelum optimasi):\n")
        for i, instr in enumerate(r["tac_before"], 1):
            lines.append(f"  {i:>3}.  {instr}")
        lines.append(f"\n  Total instruksi: {len(r['tac_before'])}")
        self._set_tab_text(self.tab_tac, "\n".join(lines))

        lines = []
        lines.append("╔══════════════════════════════════════════╗")
        lines.append("║   FASE 5: CODE OPTIMIZATION               ║")
        lines.append("╚══════════════════════════════════════════╝\n")
        lines.append("  ── Log Optimasi ──")
        for log in r["optimization_log"]:
            lines.append(f"  • {log}")
        lines.append(f"\n  ── TAC Setelah Optimasi ──\n")
        for i, instr in enumerate(r["tac_after"], 1):
            lines.append(f"  {i:>3}.  {instr}")
        lines.append(f"\n  Instruksi awal  : {len(r['tac_before'])}")
        lines.append(f"  Instruksi akhir : {len(r['tac_after'])}")
        diff = len(r["tac_before"]) - len(r["tac_after"])
        if diff > 0:
            lines.append(f"  Pengurangan     : {diff} instruksi dihapus")
        self._set_tab_text(self.tab_opt, "\n".join(lines))

        lines = []
        lines.append("╔══════════════════════════════════════════╗")
        lines.append("║   FASE 6: TARGET CODE (Pseudo-Assembly)    ║")
        lines.append("╚══════════════════════════════════════════╝\n")
        for line in r["target_code"]:
            lines.append(f"  {line}")
        self._set_tab_text(self.tab_target, "\n".join(lines))

        self.notebook.select(0)

    def _format_ast(self, node: dict, indent: int = 0) -> List[str]:
        prefix = " " * indent
        lines = []
        ntype = node.get("type", "?")

        if ntype == "DECLARATION":
            lines.append(f"{prefix}├─ DECLARATION: {node['data_type']} {node['name']}")
            lines.append(f"{prefix}│  └─ value:")
            lines.extend(self._format_ast(node["value"], indent + 5))
        elif ntype == "ASSIGNMENT":
            lines.append(f"{prefix}├─ ASSIGNMENT: {node['name']}")
            lines.append(f"{prefix}│  └─ value:")
            lines.extend(self._format_ast(node["value"], indent + 5))
        elif ntype == "PRINT":
            lines.append(f"{prefix}├─ PRINT")
            lines.append(f"{prefix}│  └─ arg:")
            lines.extend(self._format_ast(node["value"], indent + 5))
        elif ntype == "BINOP":
            lines.append(f"{prefix}├─ BINOP: {node['op']}")
            lines.append(f"{prefix}│  ├─ left:")
            lines.extend(self._format_ast(node["left"], indent + 5))
            lines.append(f"{prefix}│  └─ right:")
            lines.extend(self._format_ast(node["right"], indent + 5))
        elif ntype == "LITERAL":
            lines.append(f"{prefix}└─ LITERAL ({node['data_type']}): {node['value']}")
        elif ntype == "IDENTIFIER":
            lines.append(f"{prefix}└─ IDENT: {node['name']}")

        return lines

if __name__ == "__main__":
    app = App()
    app.mainloop()
