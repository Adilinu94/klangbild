import warnings
warnings.filterwarnings("ignore")
import mteb
bench = mteb.get_benchmark("MAEB(beta, audio-only)")
print("TASKS:", len(bench.tasks))
for t in bench.tasks:
    name = t.metadata.name
    typ = t.metadata.type
    desc = (t.metadata.description or "")[:80]
    print(f"- {name} [{typ}] {desc}")
