"""
Invocador automatizado de Claude CLI para auditorías desatendidas (guia_bucle_automatizado.md).
Ejecuta la auditoría con puntero puro, aislamiento stdin y allowlist/disallowlist de herramientas.
"""
import sys
import subprocess
from pathlib import Path

# Configurar stdout con UTF-8 para evitar errores de charmap en Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def main():
    if len(sys.argv) < 2:
        print("Uso: python scripts/auditar_bloque.py <B-XX>")
        sys.exit(1)

    block_id = sys.argv[1].upper()
    parte_path = Path(f"docs/entregas/{block_id}.md")
    acta_path = Path(f"docs/auditorias/{block_id}.md")

    if not parte_path.exists():
        print(f"Error: No existe el parte de entrega {parte_path}")
        sys.exit(1)

    prompt = (
        f"Audita {block_id} siguiendo docs/protocolo_equipo.md. "
        f"El parte está en {parte_path.as_posix()}. "
        f"Dejá el acta en {acta_path.as_posix()}."
    )

    claude_exe = r"C:\Users\ELITEBOOK\.local\bin\claude.exe"
    if not Path(claude_exe).exists():
        claude_exe = "claude"

    allowed_tools = (
        "Read Grep Glob "
        "Bash(git log:*) Bash(git show:*) Bash(git diff:*) Bash(python:*) "
        "Bash(git worktree add:*) Bash(git worktree remove:*) "
        "Edit(docs/auditorias/**) Edit(AI_LOG.md)"
    )
    disallowed_tools = "Bash(git commit:*) Bash(git add:*) Bash(git push:*)"

    cmd = [
        claude_exe,
        "-p", prompt,
        "--allowedTools", allowed_tools,
        "--disallowedTools", disallowed_tools
    ]

    print(f"Invocando Claude CLI para auditar {block_id}...")
    res = subprocess.run(
        cmd,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8"
    )

    print("=== SALIDA CLAUDE CLI ===")
    print(res.stdout)
    if res.stderr:
        print("=== STDERR CLAUDE CLI ===")
        print(res.stderr)
    print(f"=== CODIGO DE RETORNO: {res.returncode} ===")

    sys.exit(res.returncode)


if __name__ == "__main__":
    main()
