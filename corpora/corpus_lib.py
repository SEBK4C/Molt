#!/usr/bin/env python3
"""Shared logic for the imatrix / KLD-heldout corpus builders.

Disjointness contract: both builders shuffle each source with the SAME seed; the imatrix
corpus consumes items from the FRONT of the shuffled order, the KLD held-out set from the
BACK. As long as front+back never overlap (asserted), the two corpora are disjoint.

Rendering matches Ornith's chat template markers (<|im_start|>role ... <|im_end|>, tool calls
as <tool_call>{json}</tool_call>) so imatrix activations see inference-like token structure.
"""
import json
import random

IM_S, IM_E = "<|im_start|>", "<|im_end|>"


def render_chat(turns):
    """turns: [(role, content)] -> template-shaped text block."""
    out = []
    for role, content in turns:
        out.append(f"{IM_S}{role}\n{content}{IM_E}\n")
    return "".join(out) + "\n"


def render_toolcall(name, args):
    return f"<tool_call>\n{json.dumps({'name': name, 'arguments': args}, ensure_ascii=False)}\n</tool_call>"


def xlam_to_text(row):
    """Salesforce/xlam-function-calling-60k: {query, tools(json str), answers(json str)}."""
    try:
        tools = row.get("tools", "")
        answers = json.loads(row["answers"]) if isinstance(row["answers"], str) else row["answers"]
        calls = "\n".join(render_toolcall(a["name"], a.get("arguments", {})) for a in answers)
        sys_txt = f"You may call these tools:\n{tools}"
        return render_chat([("system", sys_txt), ("user", row["query"]), ("assistant", calls)])
    except Exception:
        return None


def glaive_to_text(row):
    """glaiveai/glaive-function-calling-v2: {system, chat} pre-rendered dialogue text."""
    try:
        sys_txt = (row.get("system") or "").replace("SYSTEM: ", "", 1)
        chat = row.get("chat") or ""
        chat = (chat.replace("USER: ", f"{IM_E}\n{IM_S}user\n")
                    .replace("ASSISTANT: ", f"{IM_E}\n{IM_S}assistant\n")
                    .replace("FUNCTION RESPONSE: ", f"{IM_E}\n{IM_S}tool\n"))
        return f"{IM_S}system\n{sys_txt}{chat}{IM_E}\n\n"
    except Exception:
        return None


def stack_to_text(row):
    c = row.get("content") or ""
    return c[:8000] + "\n\n" if c.strip() else None


def synthetic_tool_texts(rng, n):
    """Held-out-seed synthetic tool-syntax convos, distribution-adjacent to (never equal to)
    the frozen eval cases."""
    words = "orchid falcon timber cobalt harbor lantern mosaic pepper quartz sonnet".split()
    out = []
    for i in range(n):
        depth = rng.randint(3, 9)
        node = {"leaf": rng.randint(1, 999), "tag": rng.choice(words)}
        for d in range(depth):
            node = {f"n{d}": node, rng.choice(words): rng.randint(0, 99)}
        name = rng.choice(["update_record", "submit_form", "query_index", "patch_config"])
        user = (f"Call {name} with this exact payload:\n"
                f"{json.dumps(node, ensure_ascii=False, indent=1)}")
        out.append(render_chat([("user", user), ("assistant", render_toolcall(name, node))]))
    return out


def take_bytes(items, budget, from_back=False):
    """Greedy take whole items until byte budget; returns (texts, n_taken)."""
    seq = reversed(items) if from_back else iter(items)
    got, size = [], 0
    for t in seq:
        if t is None:
            continue
        if size + len(t.encode()) > budget:
            break
        got.append(t)
        size += len(t.encode())
    return got, size


def load_sources(log=print):
    """Load the three HF datasets; a failing source is skipped with a warning (weights are
    renormalized by the callers via the returned availability)."""
    from datasets import load_dataset
    src = {}
    try:
        src["xlam"] = list(load_dataset("Salesforce/xlam-function-calling-60k",
                                        split="train", trust_remote_code=False))
        log(f"[corpus] xlam rows: {len(src['xlam'])}")
    except Exception as e:
        log(f"[corpus] WARNING xlam unavailable: {type(e).__name__}: {e}")
    try:
        src["glaive"] = list(load_dataset("glaiveai/glaive-function-calling-v2",
                                          split="train", trust_remote_code=False))
        log(f"[corpus] glaive rows: {len(src['glaive'])}")
    except Exception as e:
        log(f"[corpus] WARNING glaive unavailable: {type(e).__name__}: {e}")
    try:
        src["code"] = list(load_dataset("bigcode/the-stack-smol", data_dir="data/python",
                                        split="train", trust_remote_code=False))
        log(f"[corpus] stack-smol python rows: {len(src['code'])}")
    except Exception as e:
        log(f"[corpus] WARNING the-stack-smol unavailable: {type(e).__name__}: {e}")
        rows = local_code_rows()
        if rows:
            src["code"] = rows
            log(f"[corpus] code fallback: {len(rows)} local source files "
                "(vendor/llama.cpp + repo; swap back to the-stack-smol after HG6)")
    return src


def local_code_rows(max_files=4000):
    """Deterministic local-code fallback while gated HF code datasets await HUMAN approval:
    real C++/Python from the pinned llama.cpp tree + this repo."""
    import os
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    roots = [os.path.join(repo, "vendor/llama.cpp/src"),
             os.path.join(repo, "vendor/llama.cpp/ggml"),
             os.path.join(repo, "vendor/llama.cpp/common"),
             os.path.join(repo, "vendor/llama.cpp/tools"),
             os.path.join(repo, "vendor/llama.cpp/examples"),
             os.path.join(repo, "vendor/llama.cpp/gguf-py"),
             os.path.join(repo, "vendor/llama.cpp/conversion"),
             os.path.join(repo, "vendor/llama.cpp/tests"),
             os.path.join(repo, "harness"), os.path.join(repo, "runner")]
    exts = (".py", ".cpp", ".h", ".hpp", ".c", ".cu", ".cuh", ".sh", ".metal", ".comp")
    files = []
    for root in roots:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = sorted(d for d in dirnames if d not in ("build", "__pycache__"))
            for fn in sorted(filenames):
                if fn.endswith(exts):
                    files.append(os.path.join(dirpath, fn))
    # root-level convert scripts are large & directly relevant
    for fn in sorted(os.listdir(os.path.join(repo, "vendor/llama.cpp"))):
        if fn.endswith(".py"):
            files.append(os.path.join(repo, "vendor/llama.cpp", fn))
    rows = []
    for p in files[:max_files]:
        try:
            with open(p, errors="ignore") as f:
                rows.append({"content": f.read(128_000)})
        except OSError:
            pass
    return rows


def build_texts(src, seed):
    """Render + shuffle every source deterministically. Returns {name: [texts]}."""
    rng = random.Random(seed)
    texts = {}
    if "xlam" in src:
        t = [xlam_to_text(r) for r in src["xlam"]]
        rng.shuffle(t)
        texts["xlam"] = t
    if "glaive" in src:
        t = [glaive_to_text(r) for r in src["glaive"]]
        rng.shuffle(t)
        texts["glaive"] = t
    if "code" in src:
        t = [stack_to_text(r) for r in src["code"]]
        rng.shuffle(t)
        texts["code"] = t
    # 12000 items ≈ 7 MB: front 2.4 MB feeds the imatrix slice, back stays free for the
    # disjoint KLD held-out slice (same rng stream prefix -> front items never change)
    texts["tool_syntax_synthetic"] = synthetic_tool_texts(random.Random(seed + 555), 12000)
    return texts
