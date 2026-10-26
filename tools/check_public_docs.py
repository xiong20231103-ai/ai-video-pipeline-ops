"""Fail closed if explanatory documents return to the public docs directory."""
from pathlib import Path


def violations(root):
    root=Path(root)
    blocked=[]
    docs=root/'docs'
    if docs.exists():
        blocked.extend(str(p.relative_to(root)).replace('\\','/') for p in docs.rglob('*') if p.is_file())
    blocked.extend(p.name for p in root.glob('交接记录_*.md') if p.is_file())
    if (root/'家庭电脑部署说明.md').is_file():blocked.append('家庭电脑部署说明.md')
    return sorted(blocked)


def main():
    found=violations(Path(__file__).resolve().parents[1])
    if found:
        print('Private documentation must not be committed to the code repository:')
        for name in found:print(name)
        return 1
    print('Public documentation boundary OK; runtime contracts live under contracts; test fixtures live under tests/fixtures.')
    return 0


if __name__=='__main__':raise SystemExit(main())
