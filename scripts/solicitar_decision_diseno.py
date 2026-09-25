"""
Invocador automatizado de Claude CLI para paradas de decisión de diseño (B-55, B-57).
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
        print("Uso: python scripts/solicitar_decision_diseno.py <B-XX>")
        sys.exit(1)

    block_id = sys.argv[1].upper()
    diag_path = Path(f"docs/diagnosticos/{block_id}_diagnostico_cruce_interno.md")
    if not diag_path.exists():
        candidates = list(Path("docs/diagnosticos").glob(f"*{block_id}*"))
        if candidates:
            diag_path = candidates[0]
        else:
            print(f"Error: No existe diagnóstico para {block_id}")
            sys.exit(1)

    acta_path = Path(f"docs/auditorias/{block_id}_decision_diseno.md")

    prompt = (
        f"Evalúa el diagnóstico de diseño para {block_id} en {diag_path.as_posix()} y docs/arquitectura_integracion.md §5. "
        f"Emite el acta de decisión formal de diseño en {acta_path.as_posix()} y formaliza la Decisión D-19 en docs/decisiones.md "
        f"con las condiciones y criterios requeridos para la implementación de {block_id}."
    )

    claude_exe = r"C:\Users\ELITEBOOK\.local\bin\claude.exe"
    if not Path(claude_exe).exists():
        claude_exe = "claude"

    allowed_tools = (
        "Read Grep Glob "
        "Bash(git log:*) Bash(git show:*) Bash(git diff:*) Bash(python:*) "
        "Bash(git worktree add:*) Bash(git worktree remove:*) "
        "Edit(docs/auditorias/**) Edit(docs/decisiones.md) Edit(AI_LOG.md)"
    )
    disallowed_tools = "Bash(git commit:*) Bash(git add:*) Bash(git push:*)"

    cmd = [
        claude_exe,
        "-p", prompt,
        "--allowedTools", allowed_tools,
        "--disallowedTools", disallowed_tools
    ]

    print(f"Invocando Claude CLI para decisión de diseño de {block_id}...")
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
