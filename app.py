from __future__ import annotations

import re
import tkinter as tk
from collections import Counter, namedtuple
from dataclasses import dataclass, field
from tkinter import messagebox, ttk
from typing import Optional


BIN_OPS = ("+", "-", "*", "/")


def is_const(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def fmt(v) -> str:
    if isinstance(v, float):
        return repr(round(v, 10))
    return str(v)


def fm(x) -> str:
    return fmt(x) if is_const(x) else str(x)


def div_int(a: int, b: int) -> int:
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b > 0) else -q


def apply_bin(op: str, a, b):
    if op == "+":
        return a + b
    if op == "-":
        return a - b
    if op == "*":
        return a * b
    if op == "/":
        if b == 0:
            raise ZeroDivisionError
        if isinstance(a, int) and isinstance(b, int):
            return div_int(a, b)
        return a / b
    raise ValueError(op)


Diag = namedtuple("Diag", "line col msg")
Msg = namedtuple("Msg", "level line text")


KEYWORDS = {"int", "float", "print"}

TOKEN_SPEC = [
    ("COMMENT", r"//[^\n]*"),
    ("FLOAT", r"\d+\.\d+"),
    ("INTEGER", r"\d+"),
    ("IDENTIFIER", r"[A-Za-z_][A-Za-z_0-9]*"),
    ("OPERATOR", r"[+\-*/]"),
    ("ASSIGN", r"="),
    ("LPAREN", r"\("),
    ("RPAREN", r"\)"),
    ("SEMICOLON", r";"),
    ("NEWLINE", r"\n"),
    ("SKIP", r"[ \t\r]+"),
    ("MISMATCH", r"."),
]
MASTER_PATTERN = re.compile("|".join(f"(?P<{n}>{p})" for n, p in TOKEN_SPEC))


@dataclass
class Token:
    kind: str
    value: str
    line: int
    col: int


def lex(src: str):
    tokens: list[Token] = []
    errors: list[Diag] = []
    line, line_start = 1, 0
    for m in MASTER_PATTERN.finditer(src):
        kind, text = m.lastgroup, m.group()
        col = m.start() - line_start + 1
        if kind == "NEWLINE":
            line += 1
            line_start = m.end()
        elif kind in ("SKIP", "COMMENT"):
            continue
        elif kind == "MISMATCH":
            errors.append(Diag(line, col, f"Karakter tidak dikenal '{text}'"))
        else:
            if kind == "IDENTIFIER" and text in KEYWORDS:
                kind = "KEYWORD"
            tokens.append(Token(kind, text, line, col))
    tokens.append(Token("EOF", "", line, len(src) - line_start + 1))
    return tokens, errors


@dataclass
class Node:
    kind: str
    value: object = None
    children: list = field(default_factory=list)
    line: int = 0
    dtype: Optional[str] = None
    vtype: Optional[str] = None

    def label(self) -> str:
        if self.kind == "Decl":
            return f"Decl [{self.dtype}] {self.value}"
        if self.kind == "Assign":
            return f"Assign {self.value}"
        if self.kind in ("BinOp", "UnOp"):
            return f"{self.kind} '{self.value}'"
        if self.kind == "Num":
            return f"Num {fmt(self.value)}"
        if self.kind == "Var":
            return f"Var {self.value}"
        return self.kind


class ParseError(Exception):
    def __init__(self, msg: str, tok: Token):
        super().__init__(msg)
        self.msg, self.tok = msg, tok


def describe(tok: Token) -> str:
    return "akhir berkas" if tok.kind == "EOF" else f"'{tok.value}'"


class Parser:
    def __init__(self, tokens: list[Token]):
        self.t = tokens
        self.i = 0
        self.errors: list[Diag] = []


    def cur(self) -> Token:
        return self.t[self.i]

    def prev(self) -> Token:
        return self.t[self.i - 1]

    def at(self, kind: str) -> bool:
        return self.cur().kind == kind

    def advance(self) -> Token:
        tok = self.t[self.i]
        if tok.kind != "EOF":
            self.i += 1
        return tok

    def expect(self, kind: str, what: str) -> Token:
        if self.at(kind):
            return self.advance()
        raise ParseError(f"Diharapkan {what}, ditemukan {describe(self.cur())}", self.cur())

    def expect_semi(self):
        if self.at("SEMICOLON"):
            return self.advance()
        cur = self.cur()
        if cur.kind in ("KEYWORD", "IDENTIFIER", "EOF"):

            p = self.prev()
            self.errors.append(Diag(p.line, p.col + len(p.value),
                                    "Diharapkan ';' di akhir pernyataan"))
            return None
        raise ParseError(f"Diharapkan ';' di akhir pernyataan, ditemukan {describe(cur)}", cur)

    def sync(self, start: int):
        while not self.at("EOF"):
            if self.at("SEMICOLON"):
                self.advance()
                break
            if self.at("KEYWORD") and self.i > start:
                break
            self.advance()
        if self.i == start and not self.at("EOF"):
            self.advance()


    def parse_program(self) -> Node:
        stmts = []
        while not self.at("EOF"):
            start = self.i
            try:
                stmts.append(self.statement())
            except ParseError as e:
                self.errors.append(Diag(e.tok.line, e.tok.col, e.msg))
                self.sync(start)
        return Node("Program", None, stmts, 1)

    def statement(self) -> Node:
        tok = self.cur()
        if tok.kind == "KEYWORD" and tok.value in ("int", "float"):
            self.advance()
            name = self.expect("IDENTIFIER", "nama variabel")
            init = []
            if self.at("ASSIGN"):
                self.advance()
                init = [self.expr()]
            self.expect_semi()
            return Node("Decl", name.value, init, tok.line, dtype=tok.value)
        if tok.kind == "KEYWORD" and tok.value == "print":
            self.advance()
            self.expect("LPAREN", "'('")
            e = self.expr()
            self.expect("RPAREN", "')'")
            self.expect_semi()
            return Node("Print", None, [e], tok.line)
        if tok.kind == "IDENTIFIER":
            self.advance()
            self.expect("ASSIGN", "'='")
            e = self.expr()
            self.expect_semi()
            return Node("Assign", tok.value, [e], tok.line)
        raise ParseError("Pernyataan tidak valid, diharapkan 'int', 'float', 'print' "
                         f"atau identifier, ditemukan {describe(tok)}", tok)

    def expr(self) -> Node:
        n = self.term()
        while self.at("OPERATOR") and self.cur().value in "+-":
            op = self.advance()
            n = Node("BinOp", op.value, [n, self.term()], op.line)
        return n

    def term(self) -> Node:
        n = self.factor()
        while self.at("OPERATOR") and self.cur().value in "*/":
            op = self.advance()
            n = Node("BinOp", op.value, [n, self.factor()], op.line)
        return n

    def factor(self) -> Node:
        tok = self.cur()
        if tok.kind == "OPERATOR" and tok.value == "-":
            self.advance()
            return Node("UnOp", "-", [self.factor()], tok.line)
        if tok.kind == "INTEGER":
            self.advance()
            return Node("Num", int(tok.value), [], tok.line, vtype="int")
        if tok.kind == "FLOAT":
            self.advance()
            return Node("Num", float(tok.value), [], tok.line, vtype="float")
        if tok.kind == "IDENTIFIER":
            self.advance()
            return Node("Var", tok.value, [], tok.line)
        if tok.kind == "LPAREN":
            self.advance()
            e = self.expr()
            self.expect("RPAREN", "')'")
            return e
        raise ParseError(f"Diharapkan ekspresi, ditemukan {describe(tok)}", tok)


def tree_lines(node: Node, prefix: str = "", last: bool = True, top: bool = True) -> list[str]:
    if top:
        out, child_prefix = [node.label()], ""
    else:
        out = [prefix + ("`-- " if last else "|-- ") + node.label()]
        child_prefix = prefix + ("    " if last else "|   ")
    for i, c in enumerate(node.children):
        out += tree_lines(c, child_prefix, i == len(node.children) - 1, False)
    return out


@dataclass
class Symbol:
    name: str
    dtype: str
    line: int
    initialized: bool
    used: bool = False


class Semantic:
    def __init__(self):
        self.table: dict[str, Symbol] = {}
        self.msgs: list[Msg] = []

    def err(self, line, text):
        self.msgs.append(Msg("ERROR", line, text))

    def warn(self, line, text):
        self.msgs.append(Msg("PERINGATAN", line, text))

    def analyze(self, prog: Node):
        for st in prog.children:
            self.stmt(st)
        for s in self.table.values():
            if not s.used:
                self.warn(s.line, f"Variabel '{s.name}' dideklarasikan tetapi tidak pernah dibaca")
        self.msgs.sort(key=lambda m: (m.line, m.level != "ERROR"))

    def check_assign(self, dtype, vtype, line, name):
        if vtype is None:
            return
        if dtype == "int" and vtype == "float":
            self.err(line, f"Ketidaksesuaian tipe: nilai float tidak dapat disimpan "
                           f"ke variabel int '{name}'")

    def stmt(self, st: Node):
        if st.kind == "Decl":
            vt = self.expr(st.children[0]) if st.children else None
            if st.value in self.table:
                self.err(st.line, f"Variabel '{st.value}' sudah dideklarasikan pada baris "
                                  f"{self.table[st.value].line}")
                return
            self.table[st.value] = Symbol(st.value, st.dtype, st.line, bool(st.children))
            self.check_assign(st.dtype, vt, st.line, st.value)
        elif st.kind == "Assign":
            vt = self.expr(st.children[0])
            sym = self.table.get(st.value)
            if sym is None:
                self.err(st.line, f"Variabel '{st.value}' belum dideklarasikan")
                return
            self.check_assign(sym.dtype, vt, st.line, st.value)
            sym.initialized = True
        elif st.kind == "Print":
            self.expr(st.children[0])

    def expr(self, n: Node) -> Optional[str]:
        if n.kind == "Num":
            return n.vtype
        if n.kind == "Var":
            sym = self.table.get(n.value)
            if sym is None:
                self.err(n.line, f"Variabel '{n.value}' belum dideklarasikan")
                n.vtype = None
                return None
            sym.used = True
            if not sym.initialized:
                self.warn(n.line, f"Variabel '{n.value}' digunakan sebelum diberi nilai")
            n.vtype = sym.dtype
            return n.vtype
        if n.kind == "UnOp":
            n.vtype = self.expr(n.children[0])
            return n.vtype
        if n.kind == "BinOp":
            lt, rt = self.expr(n.children[0]), self.expr(n.children[1])
            right = n.children[1]
            if n.value == "/" and right.kind == "Num" and right.value == 0:
                self.err(n.line, "Pembagian dengan nol")
            if lt is None or rt is None:
                n.vtype = None
            else:
                n.vtype = "float" if "float" in (lt, rt) else "int"
            return n.vtype
        return None


@dataclass
class TAC:
    op: str
    a: object = None
    b: object = None
    res: Optional[str] = None

    def text(self) -> str:
        if self.op in BIN_OPS:
            return f"{self.res} = {fm(self.a)} {self.op} {fm(self.b)}"
        if self.op == "neg":
            return f"{self.res} = -{fm(self.a)}"
        if self.op == "copy":
            return f"{self.res} = {fm(self.a)}"
        return f"print {fm(self.a)}"

    def operands(self) -> list[str]:
        return [x for x in (self.a, self.b) if isinstance(x, str)]


class Generator:
    def __init__(self, symtab: dict[str, Symbol]):
        self.symtab = symtab
        self.code: list[TAC] = []
        self.temps: set[str] = set()
        self.n = 0

    def new_temp(self) -> str:
        while True:
            self.n += 1
            name = f"t{self.n}"
            if name not in self.symtab:
                self.temps.add(name)
                return name

    def emit(self, *args, **kw):
        self.code.append(TAC(*args, **kw))

    def run(self, prog: Node) -> list[TAC]:
        for st in prog.children:
            if st.kind in ("Decl", "Assign") and st.children:
                self.emit("copy", self.expr(st.children[0]), None, st.value)
            elif st.kind == "Print":
                self.emit("print", self.expr(st.children[0]))
        return self.code

    def expr(self, n: Node):
        if n.kind in ("Num", "Var"):
            return n.value
        if n.kind == "UnOp":
            a = self.expr(n.children[0])
            t = self.new_temp()
            self.emit("neg", a, None, t)
            return t
        a, b = self.expr(n.children[0]), self.expr(n.children[1])
        t = self.new_temp()
        self.emit(n.value, a, b, t)
        return t


def infer_types(code: list[TAC], symtab: dict[str, Symbol]) -> dict[str, str]:
    types = {n: s.dtype for n, s in symtab.items()}

    def ty(x):
        if is_const(x):
            return "float" if isinstance(x, float) else "int"
        return types.get(x, "int")

    for ins in code:
        if ins.res and ins.res not in types:
            if ins.op in BIN_OPS:
                types[ins.res] = "float" if "float" in (ty(ins.a), ty(ins.b)) else "int"
            else:
                types[ins.res] = ty(ins.a)
    return types


def run_tac(code: list[TAC], types: dict[str, str]):
    env: dict = {}
    out: list[str] = []

    def val(x):
        return x if is_const(x) else env.get(x, 0)

    try:
        for ins in code:
            if ins.op == "print":
                out.append(fmt(val(ins.a)))
                continue
            if ins.op in BIN_OPS:
                v = apply_bin(ins.op, val(ins.a), val(ins.b))
            elif ins.op == "neg":
                v = -val(ins.a)
            else:
                v = val(ins.a)
            if types.get(ins.res) == "float":
                v = float(v)
            env[ins.res] = v
    except ZeroDivisionError:
        return out, env, "pembagian dengan nol saat eksekusi"
    return out, env, None


class Optimizer:
    def __init__(self, code: list[TAC], symtab: dict[str, Symbol],
                 temps: set[str], types: dict[str, str]):
        self.code = [TAC(i.op, i.a, i.b, i.res) for i in code]
        self.symtab = symtab
        self.temps = temps
        self.types = types
        self.log: list[str] = []

    def ty(self, x) -> str:
        if is_const(x):
            return "float" if isinstance(x, float) else "int"
        return self.types.get(x, "int")

    def coerce(self, res, v):
        if self.types.get(res) == "float" and isinstance(v, int):
            return float(v)
        return v

    def note(self, before: str, after: str, techniques: list[str]):
        if before != after:
            self.log.append(f"[{', '.join(techniques)}]\n      {before}   ->   {after}")


    def algebraic(self, ins: TAC):
        a, b, op = ins.a, ins.b, ins.op
        rt = "float" if "float" in (self.ty(a), self.ty(b)) else "int"
        copy = lambda v: TAC("copy", v, None, ins.res)
        if op == "+":
            if is_const(a) and a == 0 and self.ty(b) == rt:
                return copy(b), "penyederhanaan aljabar: 0 + x = x"
            if is_const(b) and b == 0 and self.ty(a) == rt:
                return copy(a), "penyederhanaan aljabar: x + 0 = x"
        elif op == "-":
            if is_const(b) and b == 0 and self.ty(a) == rt:
                return copy(a), "penyederhanaan aljabar: x - 0 = x"
        elif op == "*":
            if is_const(a) and a == 1 and self.ty(b) == rt:
                return copy(b), "penyederhanaan aljabar: 1 * x = x"
            if is_const(b) and b == 1 and self.ty(a) == rt:
                return copy(a), "penyederhanaan aljabar: x * 1 = x"
            if (is_const(a) and a == 0) or (is_const(b) and b == 0):
                return copy(0.0 if rt == "float" else 0), "penyederhanaan aljabar: x * 0 = 0"
        elif op == "/":
            if is_const(b) and b == 1 and self.ty(a) == rt:
                return copy(a), "penyederhanaan aljabar: x / 1 = x"
        return None

    def fold_and_propagate(self):
        env: dict = {}
        out: list[TAC] = []
        for ins in self.code:
            before = ins.text()
            new = TAC(ins.op, ins.a, ins.b, ins.res)
            tech: list[str] = []
            for attr in ("a", "b"):
                v = getattr(new, attr)
                if isinstance(v, str) and v in env:
                    setattr(new, attr, env[v])
                    if "propagasi konstanta" not in tech:
                        tech.append("propagasi konstanta")
            if new.op in BIN_OPS:
                if is_const(new.a) and is_const(new.b) and not (new.op == "/" and new.b == 0):
                    new = TAC("copy", apply_bin(new.op, new.a, new.b), None, new.res)
                    tech.append("constant folding")
                else:
                    r = self.algebraic(new)
                    if r:
                        new = r[0]
                        tech.append(r[1])
            elif new.op == "neg" and is_const(new.a):
                new = TAC("copy", -new.a, None, new.res)
                tech.append("constant folding")
            if new.op == "copy":
                if is_const(new.a):
                    new.a = self.coerce(new.res, new.a)
                    env[new.res] = new.a
                else:
                    env.pop(new.res, None)
            elif new.op != "print":
                env.pop(new.res, None)
            self.note(before, new.text(), tech)
            out.append(new)
        self.code = out


    def coalesce_copies(self):
        uses = Counter(o for ins in self.code for o in ins.operands())
        out: list[TAC] = []
        i = 0
        while i < len(self.code):
            ins = self.code[i]
            nxt = self.code[i + 1] if i + 1 < len(self.code) else None
            if (ins.res in self.temps and nxt is not None and nxt.op == "copy"
                    and nxt.a == ins.res and uses[ins.res] == 1):
                merged = TAC(ins.op, ins.a, ins.b, nxt.res)
                self.log.append("[eliminasi salinan]\n      "
                                f"{ins.text()}  ;  {nxt.text()}   ->   {merged.text()}")
                out.append(merged)
                i += 2
                continue
            out.append(ins)
            i += 1
        self.code = out


    def eliminate_dead(self):

        live = {i.res for i in self.code if i.res and i.res not in self.temps}
        out: list[TAC] = []
        for ins in reversed(self.code):
            if ins.op == "print":
                live |= set(ins.operands())
                out.append(ins)
            elif ins.res in live:
                live.discard(ins.res)
                live |= set(ins.operands())
                out.append(ins)
            else:
                self.log.append(f"[eliminasi kode mati]\n      {ins.text()}   ->   (dihapus)")
        out.reverse()
        self.code = out

    def run(self):
        self.fold_and_propagate()
        self.coalesce_copies()
        self.eliminate_dead()
        return self.code, self.log


def gen_target(code: list[TAC], symtab: dict[str, Symbol], types: dict[str, str]) -> list[str]:
    def ty(x):
        if is_const(x):
            return "float" if isinstance(x, float) else "int"
        return types.get(x, "int")

    def op(x):
        return f"#{fmt(x)}" if is_const(x) else str(x)

    names = list(symtab.keys())
    for ins in code:
        if ins.res and ins.res not in names:
            names.append(ins.res)

    L = ["; Mesin target hipotetis: register R1, memori bernama, operand '#' = konstanta",
         "; Awalan F pada mnemonik menandakan operasi bilangan riil (float)",
         "", ".DATA"]
    for n in names:
        L.append(f"    {n:<8} DW 0        ; {types.get(n, 'int')}")
    L += ["", ".CODE"]
    mnem = {"+": "ADD", "-": "SUB", "*": "MUL", "/": "DIV"}
    for ins in code:
        L.append(f"    ; {ins.text()}")
        if ins.op in BIN_OPS:
            f = "F" if "float" in (ty(ins.a), ty(ins.b)) else ""
            L += [f"    LOAD   R1, {op(ins.a)}",
                  f"    {f + mnem[ins.op]:<6} R1, {op(ins.b)}",
                  f"    STORE  {ins.res}, R1"]
        elif ins.op == "neg":
            f = "F" if ty(ins.a) == "float" else ""
            L += [f"    LOAD   R1, {op(ins.a)}", f"    {f}NEG    R1",
                  f"    STORE  {ins.res}, R1"]
        elif ins.op == "copy":
            L += [f"    LOAD   R1, {op(ins.a)}", f"    STORE  {ins.res}, R1"]
        else:
            f = "F" if ty(ins.a) == "float" else ""
            L += [f"    LOAD   R1, {op(ins.a)}", f"    {f}PRINT  R1"]
    L.append("    HALT")
    return L


STAGES = [("lex", "1. Analisis Leksikal"), ("parse", "2. Analisis Sintaks (Parsing)"),
          ("sem", "3. Analisis Semantik"), ("tac", "4. Kode Antara"),
          ("opt", "5. Optimasi Kode"), ("target", "6. Kode Target")]

GRAMMAR = [
    "  program    -> statement*",
    "  statement  -> ('int' | 'float') ID ['=' expr] ';'",
    "              | ID '=' expr ';'",
    "              | 'print' '(' expr ')' ';'",
    "  expr       -> term (('+' | '-') term)*",
    "  term       -> factor (('*' | '/') factor)*",
    "  factor     -> '-' factor | INTEGER | FLOAT | ID | '(' expr ')'",
]

SKIP_TEXT = "(Tahap dilewati karena tahap sebelumnya mengandung kesalahan.)"


@dataclass
class Result:
    texts: dict = field(default_factory=dict)
    status: dict = field(default_factory=dict)
    detail: dict = field(default_factory=dict)
    error_lines: set = field(default_factory=set)
    n_tokens: int = 0


def numbered(lines: list[str]) -> list[str]:
    return [f"{i:>3}  {s}" for i, s in enumerate(lines, 1)]


def compile_source(src: str) -> Result:
    r = Result()
    for k, _ in STAGES:
        r.status[k], r.detail[k], r.texts[k] = "DILEWATI", "-", SKIP_TEXT
    sim = None

    def finish() -> Result:
        S = ["== RINGKASAN HASIL KOMPILASI ==", "",
             f"{'Tahap':<32}{'Status':<12}Keterangan", "-" * 72]
        for k, name in STAGES:
            S.append(f"{name:<32}{r.status[k]:<12}{r.detail[k]}")
        S.append("")
        if all(r.status[k] == "BERHASIL" for k, _ in STAGES):
            S.append("[OK] Kompilasi selesai tanpa kesalahan.")
        else:
            S.append("[ERROR] Kompilasi dihentikan karena terdapat kesalahan. "
                     "Lihat tab tahap yang berstatus GAGAL.")
        if sim:
            S += ["", "== SIMULASI EKSEKUSI KODE ANTARA =="]
            S.append("Keluaran sebelum optimasi : " + (", ".join(sim[0]) or "(kosong)"))
            S.append("Keluaran sesudah optimasi : " + (", ".join(sim[1]) or "(kosong)"))
            S.append(("[OK] " if sim[2] else "[ERROR] ") +
                     ("Hasil sebelum dan sesudah optimasi SAMA (optimasi mempertahankan semantik)."
                      if sim[2] else "Hasil sebelum dan sesudah optimasi BERBEDA."))
            if sim[3]:
                S.append(f"[PERINGATAN] Eksekusi berhenti: {sim[3]}.")
        r.texts["summary"] = "\n".join(S)
        return r


    tokens, lex_errors = lex(src)
    r.n_tokens = len(tokens) - 1
    L = ["== ANALISIS LEKSIKAL ==", f"Jumlah token : {r.n_tokens}", "",
         f"{'No':<5}{'Baris':<7}{'Kol':<6}{'Jenis Token':<14}Lexeme", "-" * 52]
    for i, t in enumerate(tokens[:-1], 1):
        L.append(f"{i:<5}{t.line:<7}{t.col:<6}{t.kind:<14}{t.value}")
    for d in lex_errors:
        L.append(f"[ERROR] Baris {d.line}, kolom {d.col}: {d.msg}")
        r.error_lines.add(d.line)
    if not lex_errors:
        L += ["", "[OK] Seluruh karakter berhasil dikenali."]
    r.texts["lex"] = "\n".join(L)
    if lex_errors:
        r.status["lex"], r.detail["lex"] = "GAGAL", f"{len(lex_errors)} kesalahan leksikal"
        return finish()
    r.status["lex"], r.detail["lex"] = "BERHASIL", f"{r.n_tokens} token"


    parser = Parser(tokens)
    prog = parser.parse_program()
    P = ["== ANALISIS SINTAKS (PARSING) ==", "Metode : recursive descent (LL(1))", "",
         "Tata bahasa:"] + GRAMMAR + [""]
    if parser.errors:
        for d in parser.errors:
            P.append(f"[ERROR] Baris {d.line}, kolom {d.col}: {d.msg}")
            r.error_lines.add(d.line)
        r.texts["parse"] = "\n".join(P)
        r.status["parse"], r.detail["parse"] = "GAGAL", f"{len(parser.errors)} kesalahan sintaks"
        return finish()
    P += ["[OK] Struktur program sesuai tata bahasa.", "",
          "Pohon sintaks abstrak (AST):"] + tree_lines(prog)
    r.texts["parse"] = "\n".join(P)
    r.status["parse"], r.detail["parse"] = "BERHASIL", f"{len(prog.children)} pernyataan"


    sem = Semantic()
    sem.analyze(prog)
    errs = [m for m in sem.msgs if m.level == "ERROR"]
    warns = [m for m in sem.msgs if m.level != "ERROR"]
    S = ["== ANALISIS SEMANTIK ==", "", "Tabel simbol:",
         f"{'Nama':<12}{'Tipe':<8}{'Baris':<8}{'Diinisialisasi':<16}Dibaca", "-" * 54]
    for s in sem.table.values():
        S.append(f"{s.name:<12}{s.dtype:<8}{s.line:<8}{'ya' if s.initialized else 'tidak':<16}"
                 f"{'ya' if s.used else 'tidak'}")
    if not sem.table:
        S.append("(kosong)")
    S.append("")
    for m in sem.msgs:
        S.append(f"[{m.level}] Baris {m.line}: {m.text}")
        if m.level == "ERROR":
            r.error_lines.add(m.line)
    if not sem.msgs:
        S.append("[OK] Tidak ditemukan masalah semantik.")
    elif not errs:
        S += ["", "[OK] Tidak ada kesalahan semantik (hanya peringatan)."]
    r.texts["sem"] = "\n".join(S)
    if errs:
        r.status["sem"], r.detail["sem"] = "GAGAL", f"{len(errs)} kesalahan, {len(warns)} peringatan"
        return finish()
    r.status["sem"], r.detail["sem"] = "BERHASIL", f"{len(sem.table)} variabel, {len(warns)} peringatan"


    gen = Generator(sem.table)
    tac = gen.run(prog)
    types = infer_types(tac, sem.table)
    T = ["== KODE ANTARA (THREE-ADDRESS CODE) ==", f"Jumlah instruksi : {len(tac)}", ""]
    T += numbered([i.text() for i in tac]) or ["(tidak ada instruksi)"]
    r.texts["tac"] = "\n".join(T)
    r.status["tac"], r.detail["tac"] = "BERHASIL", f"{len(tac)} instruksi"


    opt = Optimizer(tac, sem.table, gen.temps, types)
    optimized, log = opt.run()
    O = ["== OPTIMASI KODE ==", "", f"Kode antara SEBELUM optimasi ({len(tac)} instruksi):"]
    O += numbered([i.text() for i in tac]) or ["(kosong)"]
    O += ["", f"Kode antara SESUDAH optimasi ({len(optimized)} instruksi):"]
    O += numbered([i.text() for i in optimized]) or ["(kosong)"]
    O += ["", "Daftar transformasi yang diterapkan:"]
    O += [f"  {i}. {s}" for i, s in enumerate(log, 1)] or ["  (tidak ada peluang optimasi)"]
    O += ["", f"Hasil: {len(tac)} -> {len(optimized)} instruksi "
              f"(berkurang {len(tac) - len(optimized)}).",
          "Catatan: nilai akhir setiap variabel dianggap teramati, sehingga hanya "
          "temporer dan penyimpanan yang tertimpa sebelum dibaca yang dihapus."]
    r.texts["opt"] = "\n".join(O)
    r.status["opt"], r.detail["opt"] = "BERHASIL", f"{len(tac)} -> {len(optimized)} instruksi"


    target = gen_target(optimized, sem.table, types)
    r.texts["target"] = "\n".join(["== KODE TARGET ==", ""] + target)
    r.status["target"], r.detail["target"] = "BERHASIL", f"{len(target)} baris"


    out1, env1, e1 = run_tac(tac, types)
    out2, env2, e2 = run_tac(optimized, types)
    vars1 = {k: v for k, v in env1.items() if k in sem.table}
    vars2 = {k: v for k, v in env2.items() if k in sem.table}
    sim = (out1, out2, out1 == out2 and vars1 == vars2 and bool(e1) == bool(e2), e1 or e2)
    return finish()


EXAMPLES = [
    ("Aritmetika dasar",
     "int a = 10;\nint b = 20;\nint c = a + b * 2;\nprint(c);\n"),
    ("Peluang optimasi",
     "int x = 4;\nint y = x * 1 + 0;\nint z = (2 + 3) * x;\n"
     "int w = 8;\nw = 15;\nprint(y);\nprint(z);\nprint(w);\n"),
    ("Tipe int dan float",
     "float r = 2.5;\nint n = 4;\nfloat luas = 3.14 * r * r;\n"
     "float rata = (luas + n) / 2;\nprint(luas);\nprint(rata);\n"),
    ("Ekspresi bertingkat dan unary minus",
     "int p = 7;\nint q = -p + 3 * (p - 2);\nint s = q / 2;\nprint(q);\nprint(s);\n"),
    ("Kesalahan leksikal",
     "int a = 5;\nint b = a # 3;\nfloat c = 2.5 @ 1;\nprint(b);\n"),
    ("Kesalahan sintaks",
     "int a = 10\nint b = (a + 2;\nprint(a b);\n"),
    ("Kesalahan semantik",
     "int a = 5;\nint a = 6;\nfloat f = 2.5;\nint g = f * 2;\n"
     "k = a + 1;\nprint(m);\nint z = a / 0;\n"),
]


THEMES = {
    "Gelap": dict(bg="#23272e", panel="#2c313a", editor="#1d2026", fg="#d4d8df", dim="#8b93a1",
                  sel="#394b63", border="#3b4252", button="#353c48", active="#414959",
                  err="#e0838c", warn="#d8a657", ok="#93c488", head="#a9c1e8",
                  gutter="#22262c", gutter_fg="#657083", errline="#4b2c33"),
    "Hangat": dict(bg="#e6e0d1", panel="#ddd6c5", editor="#f1ecdf", fg="#2f2b24", dim="#6b6454",
                   sel="#c8d3e0", border="#c4bba6", button="#d3cbb7", active="#c6bda7",
                   err="#a83a3a", warn="#8a5a10", ok="#3d6b2f", head="#35506f",
                   gutter="#e3dccb", gutter_fg="#8a826f", errline="#f0cfc7"),
}
THEME_ORDER = ["Gelap", "Hangat"]


class App(tk.Tk):
    ROWS = [("summary", "Ringkasan"), ("lex", "1. Leksikal"), ("parse", "2. Parser"),
            ("sem", "3. Semantik"), ("tac", "4. Kode Antara"), ("opt", "5. Optimasi"),
            ("target", "6. Kode Target")]

    SHORT = {"lex": "1. Leksikal", "parse": "2. Parser", "sem": "3. Semantik",
             "tac": "4. Kode Antara", "opt": "5. Optimasi", "target": "6. Kode Target"}

    WELCOME = ("Selamat datang di Laboratorium Teknik Kompilasi.\n\n"
               "1. Tulis program pada editor di kiri, atau klik 'Contoh'.\n"
               "2. Klik 'Kompilasi' (atau tekan Ctrl+Enter).\n"
               "3. Pilih tahap pada daftar di sebelah kiri panel ini untuk melihat hasilnya.\n"
               "4. Klik 'Tema' untuk berganti antara tampilan gelap dan hangat.\n\n"
               "Sintaks yang didukung: deklarasi int/float, assignment, operator + - * /,\n"
               "tanda kurung, minus unary, print(...), dan komentar //.")

    def __init__(self):
        super().__init__()
        self.title("Laboratorium Teknik Kompilasi - Python")
        self.geometry("1200x720")
        self.minsize(980, 580)
        self.example_idx = -1
        self.theme_idx = 0
        self.texts: dict[str, str] = {}
        self.style = ttk.Style(self)
        try:
            self.style.theme_use("clam")
        except tk.TclError:
            pass
        self._build()
        self.apply_theme()
        self.load_example()
        self.bind("<Control-Return>", lambda e: self.compile())

    def apply_theme(self):
        name = THEME_ORDER[self.theme_idx]
        t = THEMES[name]
        st = self.style
        self.configure(bg=t["bg"])
        st.configure(".", font=("Segoe UI", 10), background=t["bg"], foreground=t["fg"])
        st.configure("TFrame", background=t["bg"])
        st.configure("Bar.TFrame", background=t["panel"])
        st.configure("Bar.TLabel", background=t["panel"], foreground=t["fg"])
        st.configure("BarTitle.TLabel", background=t["panel"], foreground=t["head"],
                     font=("Segoe UI", 11, "bold"))
        st.configure("Cap.TLabel", background=t["panel"], foreground=t["dim"],
                     font=("Segoe UI", 9, "bold"), padding=(8, 4))
        st.configure("Status.TLabel", background=t["panel"], foreground=t["dim"],
                     font=("Segoe UI", 9), padding=(8, 3))
        st.configure("TButton", background=t["button"], foreground=t["fg"], bordercolor=t["border"],
                     lightcolor=t["button"], darkcolor=t["button"], focuscolor=t["button"],
                     padding=(12, 4), relief="flat")
        st.map("TButton", background=[("active", t["active"]), ("pressed", t["active"])],
               foreground=[("active", t["fg"])])
        st.configure("TSeparator", background=t["border"])
        st.configure("TPanedwindow", background=t["bg"])
        st.configure("Treeview", background=t["editor"], fieldbackground=t["editor"],
                     foreground=t["fg"], rowheight=28, borderwidth=0, font=("Segoe UI", 10),
                     bordercolor=t["border"], lightcolor=t["editor"], darkcolor=t["editor"])
        st.configure("Treeview.Heading", background=t["panel"], foreground=t["dim"],
                     font=("Segoe UI", 9, "bold"), borderwidth=0, relief="flat")
        st.map("Treeview", background=[("selected", t["sel"])], foreground=[("selected", t["fg"])])
        st.map("Treeview.Heading", background=[("active", t["panel"])])
        for orient in ("Vertical", "Horizontal"):
            st.configure(f"{orient}.TScrollbar", background=t["button"], troughcolor=t["bg"],
                         bordercolor=t["bg"], arrowcolor=t["dim"], lightcolor=t["button"],
                         darkcolor=t["button"])
            st.map(f"{orient}.TScrollbar", background=[("active", t["active"])])
        for w in (self.src, self.out):
            w.configure(bg=t["editor"], fg=t["fg"], insertbackground=t["fg"],
                        selectbackground=t["sel"], selectforeground=t["fg"])
        self.gutter.configure(bg=t["gutter"], fg=t["gutter_fg"])
        self.src.tag_configure("errline", background=t["errline"])
        self.out.tag_configure("err", foreground=t["err"])
        self.out.tag_configure("warn", foreground=t["warn"])
        self.out.tag_configure("ok", foreground=t["ok"])
        self.out.tag_configure("head", foreground=t["head"], font=("Consolas", 10, "bold"))
        self.nav.tag_configure("ok", foreground=t["ok"])
        self.nav.tag_configure("fail", foreground=t["err"])
        self.nav.tag_configure("skip", foreground=t["dim"])
        self.theme_var.set(f"Tema: {name}")

    def toggle_theme(self):
        self.theme_idx = (self.theme_idx + 1) % len(THEME_ORDER)
        self.apply_theme()

    def _scroll_text(self, parent, **kw):
        frame = ttk.Frame(parent)
        txt = tk.Text(frame, wrap="none", font=("Consolas", 10), relief="flat", bd=0,
                      padx=8, pady=6, highlightthickness=0, **kw)
        ys = ttk.Scrollbar(frame, orient="vertical")
        xs = ttk.Scrollbar(frame, orient="horizontal", command=txt.xview)
        txt.configure(xscrollcommand=xs.set)
        ys.pack(side="right", fill="y")
        xs.pack(side="bottom", fill="x")
        txt.pack(side="left", fill="both", expand=True)
        return frame, txt, ys

    def _build(self):
        bar = ttk.Frame(self, style="Bar.TFrame", padding=(10, 6))
        bar.pack(fill="x")
        ttk.Label(bar, text="Lab Teknik Kompilasi", style="BarTitle.TLabel").pack(side="left")
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=12)
        ttk.Button(bar, text="Kompilasi", command=self.compile).pack(side="left", padx=(0, 4))
        ttk.Button(bar, text="Contoh", command=self.load_example).pack(side="left", padx=4)
        ttk.Button(bar, text="Bersih", command=self.clear).pack(side="left", padx=4)
        self.theme_var = tk.StringVar()
        ttk.Button(bar, textvariable=self.theme_var, command=self.toggle_theme).pack(side="right")
        self.example_label = tk.StringVar()
        ttk.Label(bar, textvariable=self.example_label, style="Bar.TLabel").pack(side="right", padx=12)

        self.status = tk.StringVar(value="Siap.")
        ttk.Label(self, textvariable=self.status, style="Status.TLabel").pack(side="bottom", fill="x")

        paned = ttk.PanedWindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True)

        left = ttk.Frame(paned)
        paned.add(left, weight=2)
        ttk.Label(left, text="EDITOR KODE SUMBER", style="Cap.TLabel").pack(fill="x")
        ed = ttk.Frame(left)
        ed.pack(fill="both", expand=True)
        ys = ttk.Scrollbar(ed, orient="vertical", command=self._yview)
        xs = ttk.Scrollbar(ed, orient="horizontal")
        ys.pack(side="right", fill="y")
        xs.pack(side="bottom", fill="x")
        self.gutter = tk.Text(ed, width=4, font=("Consolas", 10), relief="flat", bd=0, padx=4,
                              pady=6, highlightthickness=0, state="disabled", cursor="arrow",
                              takefocus=0)
        self.gutter.tag_configure("r", justify="right")
        self.gutter.pack(side="left", fill="y")
        self.src = tk.Text(ed, wrap="none", font=("Consolas", 10), relief="flat", bd=0, padx=8,
                           pady=6, undo=True, highlightthickness=0, tabs=("1c",),
                           yscrollcommand=lambda a, b: (ys.set(a, b), self.gutter.yview_moveto(a)),
                           xscrollcommand=xs.set)
        xs.configure(command=self.src.xview)
        self.src.pack(side="left", fill="both", expand=True)
        self.src.bind("<<Modified>>", self._on_modified)
        self.src.bind("<KeyRelease>", self._update_cursor)
        self.src.bind("<ButtonRelease-1>", self._update_cursor)

        right = ttk.Frame(paned)
        paned.add(right, weight=3)
        ttk.Label(right, text="HASIL ANALISIS", style="Cap.TLabel").pack(fill="x")
        inner = ttk.PanedWindow(right, orient="horizontal")
        inner.pack(fill="both", expand=True)

        navf = ttk.Frame(inner)
        inner.add(navf, weight=0)
        self.nav = ttk.Treeview(navf, columns=("name", "status"), show="headings",
                                selectmode="browse", height=8)
        self.nav.heading("name", text="Tahap")
        self.nav.heading("status", text="Status")
        self.nav.column("name", width=140, stretch=True)
        self.nav.column("status", width=76, stretch=False, anchor="center")
        for key, name in self.ROWS:
            self.nav.insert("", "end", iid=key, values=(name, ""))
        self.nav.pack(fill="both", expand=True)
        self.nav.bind("<<TreeviewSelect>>", self._on_select)

        outf, self.out, oys = self._scroll_text(inner, state="disabled")
        oys.configure(command=self.out.yview)
        self.out.configure(yscrollcommand=oys.set)
        inner.add(outf, weight=1)

    def _yview(self, *args):
        self.src.yview(*args)
        self.gutter.yview(*args)

    def _on_modified(self, _e=None):
        if self.src.edit_modified():
            self._update_gutter()
            self.src.edit_modified(False)

    def _update_gutter(self):
        n = int(self.src.index("end-1c").split(".")[0])
        self.gutter.configure(state="normal")
        self.gutter.delete("1.0", "end")
        self.gutter.insert("1.0", "\n".join(str(i) for i in range(1, n + 1)), ("r",))
        self.gutter.configure(state="disabled")
        self.gutter.yview_moveto(self.src.yview()[0])

    def _update_cursor(self, _e=None):
        ln, col = self.src.index("insert").split(".")
        self.status.set(f"Baris {ln}, kolom {int(col) + 1}")

    def show(self, key: str):
        text = self.texts.get(key, "")
        w = self.out
        w.configure(state="normal")
        w.delete("1.0", "end")
        for line in text.split("\n"):
            tag = None
            if line.startswith("[ERROR]"):
                tag = "err"
            elif line.startswith("[PERINGATAN]"):
                tag = "warn"
            elif line.startswith("[OK]"):
                tag = "ok"
            elif line.startswith("== "):
                tag = "head"
            w.insert("end", line + "\n", (tag,) if tag else ())
        w.configure(state="disabled")

    def _on_select(self, _e=None):
        sel = self.nav.selection()
        if sel:
            self.show(sel[0])

    def select_row(self, key: str):
        if self.nav.selection() == (key,):
            self.show(key)
        else:
            self.nav.selection_set(key)

    def reset_outputs(self):
        self.texts = {k: "" for k, _ in self.ROWS}
        self.texts["summary"] = self.WELCOME
        for key, name in self.ROWS:
            self.nav.item(key, values=(name, ""), tags=())
        self.select_row("summary")

    def compile(self):
        src = self.src.get("1.0", "end-1c")
        self.src.tag_remove("errline", "1.0", "end")
        if not src.strip():
            messagebox.showwarning("Kode kosong", "Tulis kode program atau pilih 'Contoh' dahulu.")
            return
        res = compile_source(src)
        self.texts = dict(res.texts)
        tagmap = {"BERHASIL": "ok", "GAGAL": "fail", "DILEWATI": "skip"}
        for key, _ in STAGES:
            self.nav.item(key, values=(self.SHORT[key], res.status[key].capitalize()),
                          tags=(tagmap[res.status[key]],))
        self.nav.item("summary", values=("Ringkasan", ""), tags=())
        for ln in res.error_lines:
            self.src.tag_add("errline", f"{ln}.0", f"{ln}.end+1c")
        failed = [k for k, _ in STAGES if res.status[k] == "GAGAL"]
        if failed:
            self.select_row(failed[0])
            self.status.set(f"Kompilasi gagal pada tahap: {dict(STAGES)[failed[0]]}.")
        else:
            self.select_row("summary")
            self.status.set("Kompilasi berhasil.")

    def load_example(self):
        self.example_idx = (self.example_idx + 1) % len(EXAMPLES)
        name, code = EXAMPLES[self.example_idx]
        self.src.tag_remove("errline", "1.0", "end")
        self.src.delete("1.0", "end")
        self.src.insert("1.0", code)
        self.example_label.set(f"Contoh {self.example_idx + 1}/{len(EXAMPLES)}: {name}")
        self.reset_outputs()
        self.status.set("Contoh dimuat. Klik 'Kompilasi' untuk memproses.")

    def clear(self):
        self.src.tag_remove("errline", "1.0", "end")
        self.src.delete("1.0", "end")
        self.example_label.set("")
        self.reset_outputs()
        self.status.set("Editor dan hasil analisis dibersihkan.")


if __name__ == "__main__":
    App().mainloop()