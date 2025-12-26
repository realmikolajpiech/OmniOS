import logging, sys, os, time, threading, json, subprocess
from flask import Flask, request, jsonify
import requests
from simpleeval import SimpleEval

# Silence logs
logging.getLogger('werkzeug').setLevel(logging.ERROR)
logging.basicConfig(level=logging.INFO)
app = Flask(__name__)

HOME = os.path.expanduser("~")
MODEL_DIR = os.path.join(HOME, ".local/share/ai-models")
# Matches setup-dev.sh
MODEL_FILENAME = "gemma-3-1b-it-Q8_0.gguf"
MODEL_PATH = os.path.join(MODEL_DIR, MODEL_FILENAME)

DB_PATH = os.path.join(HOME, ".local/share/ai-memory-db")
SEARXNG_URL = "http://127.0.0.1:8888/search"

llm = None
embed_model = None
db_conn = None
init_error = None

# Thread Lock
main_lock = threading.Lock()
fast_lock = threading.Lock()
abort_fast_event = threading.Event()

# Fast Action Model (Shared with Main in this config to save VRAM)
fast_model = None
fast_loading_started = False
fast_model_error = None

# --- SHORTCUTS ---
COMMON_SHORTCUTS = {
    "yt": "https://www.youtube.com",
    "gh": "https://github.com",
    "x": "https://x.com",
    "red": "https://reddit.com",
    "map": "https://www.google.com/maps",
    "chat": "https://chatgpt.com"
}

def ensure_model_loaded():
    """Smart Loader: Loads models separately or unified based on config"""
    global llm, fast_model, init_error, embed_model, db_conn, fast_lock, main_lock
    
    if llm and fast_model: return

    logging.info("Smart Loader: Starting...")
    
    # 1. DB Connect
    logging.info("Smart Loader: Connecting to DB...")
    if db_conn is None:
        try: 
            if os.path.exists(DB_PATH): 
                import lancedb
                db_conn = lancedb.connect(DB_PATH)
                logging.info("Smart Loader: DB Connected.")
            else:
                logging.info("Smart Loader: DB Path not found, skipping.")
        except Exception as e:
            logging.error(f"Smart Loader: DB Error: {e}")

    # 2. Imports
    logging.info("Smart Loader: Importing Libraries...")
    try:
        from llama_cpp import Llama
        # from sentence_transformers import SentenceTransformer # Moved strictly to embeddings block
        # import torch
        logging.info("Smart Loader: Libraries Imported.")
    except Exception as e:
        logging.error(f"Smart Loader: Import Error: {e}")
        init_error = str(e)
        return

    # 3. Load Model
    if not os.path.exists(MODEL_PATH):
        init_error = f"Model not found at {MODEL_PATH}"
        logging.error(init_error)
        return

    n_gpu_layers = -1 # All layers to GPU if possible
    
    with main_lock:
        if llm and fast_model: return 
        logging.info(f"Loading Model: {MODEL_FILENAME}")
        try:
            shared_model = Llama(
                model_path=MODEL_PATH, 
                n_ctx=4096, 
                n_threads=4, 
                n_gpu_layers=n_gpu_layers, 
                verbose=False
            )
            llm = shared_model
            fast_model = shared_model
            
            # Helper for simple completions
            # Monkey patch or wrapper if custom logic needed, but Llama object is callable
            
            fast_lock = main_lock 
            logging.info("Model Loaded successfully.")
        except Exception as e:
            logging.error(f"Model Load Error: {e}")
            init_error = str(e)

    # 4. Embeddings (CPU/GPU)
    try:
        from sentence_transformers import SentenceTransformer
        import torch
        device = 'cpu' # Force CPU for now to be safe
        logging.info(f"Loading Embeddings on device: {device.upper()}")
        embed_model = SentenceTransformer('all-MiniLM-L6-v2', device=device)
    except Exception as e:
        logging.error(f"Embeddings disabled due to import error: {e}")
        embed_model = None

def ensure_fast_model():
    ensure_model_loaded()

def ensure_main_model():
    ensure_model_loaded()

def search_api(query, categories='general'):
    try:
        logging.info(f"Searching SearXNG for: '{query}' (Categories: {categories})")
        params = {
            'q': query, 
            'format': 'json', 
            'categories': categories,
            'language': 'en-US' 
        }
        resp = requests.get(SEARXNG_URL, params=params, timeout=5.0)
        if resp.status_code == 200:
            results = resp.json().get('results', [])
            return results
    except Exception as e:
        logging.error(f"Search API Error: {e}")
    return []

def perform_web_search(query):
    logging.info(f"Performing SearXNG Search for: {query}")
    try:
        results = search_api(query, categories='general')
        if not results: return "No search results found."
        
        text_res = []
        for i, res in enumerate(results):
            if i >= 3: break
            title = res.get('title', 'No Title')
            url = res.get('url', ' ')
            content = res.get('content', ' '.strip()) or res.get('snippet', ' '.strip())
            if content:
                text_res.append(f"Source: {title} ({url})\nContent: {content}")
        
        return "\n\n".join(text_res)
    except Exception as e:
        return f"Search failed: {str(e)}"

def get_navigation_result(query):
    try:
        params = {'q': query, 'format': 'json'}
        resp = requests.get(SEARXNG_URL, params=params, timeout=3.0)
        if resp.status_code == 200:
            results = resp.json().get('results', [])
            if results:
                first = results[0]
                return {
                    "url": first.get('url'),
                    "title": first.get('title', 'Link'),
                    "description": first.get('content') or first.get('snippet', ' '.strip())
                }
    except: pass
    return None

def get_person_result(name):
    # Simplified logic for porting (can be expanded later)
    try:
        with open("/tmp/person_debug.log", "a") as f:
            f.write(f"Entering get_person_result for: {name}\n")
        params = {'q': name, 'format': 'json', 'categories': 'general', 'language': 'en-US'}
        resp = requests.get(SEARXNG_URL, params=params, timeout=4.0)
        
        if resp.status_code == 200:
            results = resp.json().get('results', [])
            with open("/tmp/person_debug.log", "a") as f:
                f.write(f"Query: {name}\nStatus: {resp.status_code}\nResults: {len(results)}\nFirst: {results[0] if results else 'None'}\n{'-'*20}\n")
            if results:
                best = results[0]
                image_url = None
                # Basic direct image fetch via search if needed
                return {
                    "type": "person",
                    "name": best.get('title', name),
                    "description": best.get('content') or best.get('snippet', ''),
                    "url": best.get('url'),
                    "image": None # Placeholder for now
                }
    except Exception as e:
        # Fallback: Wikipedia API
        try:
            # Clean name for URL (spaces to underscores)
            wiki_name = name.strip().replace(" ", "_")
            url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{wiki_name}"
            headers = {"User-Agent": "OmniOS/1.0 (internal-dev)"}
            r = requests.get(url, headers=headers, timeout=4)
            if r.status_code == 200:
                data = r.json()
                if data.get('type') == 'standard':
                   return {
                       "type": "person",
                       "name": data.get('title', name),
                       "description": data.get('extract', ' '),
                       "url": data.get('content_urls', {}).get('desktop', {}).get('page', ''),
                       "image": data.get('thumbnail', {}).get('source')
                   }
        except: pass
    pass
    return None

def get_place_result(query):
    # Simplified logic for porting
    try:
        params = {'q': query, 'format': 'json', 'categories': 'map'}
        resp = requests.get(SEARXNG_URL, params=params, timeout=4.0)
        if resp.status_code == 200:
            results = resp.json().get('results', [])
            if results:
                best = results[0]
                return {
                    "type": "place",
                    "name": best.get('title', query),
                    "address": best.get('content', '') or best.get('address', {}).get('road', ''),
                    "latitude": best.get('latitude'),
                    "longitude": best.get('longitude'),
                    "url": best.get('url'),
                    "image": None
                }
    except: pass
    return None

def resolve_app_metadata(app_name):
    # User requested generic web search for "first link"
    try:
        # Use html.duckduckgo.com for non-JS version (robust fallback)
        url = "https://html.duckduckgo.com/html/"
        params = {"q": f"{app_name} official website"}
        headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36"}
        
        # Use POST to emulate standard form submission
        resp = requests.post(url, data=params, headers=headers, timeout=5)
        
        if resp.status_code == 200:
            import re
            # Regex to find the first result link: class="result__a" href="..."
            # This is standard DDG HTML structure
            match = re.search(r'class="result__a" href="([^"]+)"', resp.text)
            if match:
                final_url = match.group(1)
                return {
                    "image": None, # Omni will fetch favicon
                    "website": final_url
                }
    except: pass
    return None

def perform_calculation(expression):
    try:
        lower_input = expression.lower()
        for prefix in ["calculate ", "what is ", "solve "]:
            if lower_input.startswith(prefix):
                expression = expression[len(prefix):]
        s = SimpleEval()
        result = s.eval(expression)
        return (f"Expression: {expression}\nResult: {result}")
    except Exception as e:
        return f"Error calculating '{expression}': {str(e)}"

@app.route('/ask', methods=['POST'])
def ask():
    abort_fast_event.set()
    ensure_main_model()

    if not llm:
        return jsonify({"answer": f"Error: Model failed to load. Reason: {init_error}"})

    try: req = request.get_json(force=True)
    except: return jsonify({"answer": "Error: Bad JSON"}), 400
    
    query = req.get('query', ' '.strip())
    
    # Simple Routing Logic (Rule based + Lite LLM if needed)
    # For speed in this port, we rely on semantic routing or just asking LLM directly
    
    context_text = ""
    source_type = "None"
    
    # Very basic keywords for now, can use LLM router
    if any(x in query.lower() for x in ["weather", "news", "who is", "what is"]):
         source_type = "Internet"
         context_text = f"--- Web Search Results ---\n{perform_web_search(query)}\n"
    elif any(x in query for x in ["+", "*", "/", "sqrt"]):
         source_type = "Calculator"
         context_text = f"--- Calculation Result ---\n{perform_calculation(query)}\n"

    prompt = (
        f"<|im_start|>system\nYou are Omni, a smart OS assistant.\n"
        f"Context Source: {source_type}\n"
        f"Context Data:\n{context_text or 'No context.'}\n\n"
        f"RULES:\n"
        f"1. Answer concisely.\n"
        f"2. Use context if available.\n"
        f"<|im_end|>\n"
        f"<|im_start|>user\n{query}<|im_end|>\n"
        f"<|im_start|>assistant\n"
    )

    try:
        abort_fast_event.clear()
        with main_lock:
            output = llm(
                prompt, max_tokens=1024, stop=["<|im_start|>", "<|im_end|>", "<|endoftext|>"], 
                echo=False, temperature=0.7
            )
        answer = output['choices'][0]['text'].strip()
    except Exception as e: answer = f"Error: {e}"
    
    return jsonify({"answer": answer})

@app.route('/search', methods=['POST'])
def search_endpoint():
    ensure_main_model()
    if not db_conn or not embed_model:
        return jsonify({"results": []})

    try: req = request.get_json(force=True)
    except: return jsonify({"results": []}), 400
    
    query = req.get('query', "").strip()
    if not query: return jsonify({"results": []})

    results = []
    try:
        tbl = db_conn.open_table("files")
        res = tbl.search(embed_model.encode(query)).limit(3).to_pandas()
        if not res.empty:
            for _, row in res.iterrows():
                if row.get('_distance', 0) < 1.1:
                    results.append({
                        "name": row['filename'],
                        "path": row['path'],
                        "score": float(row.get('_distance', 0)),
                        "type": "file"
                    })
    except: pass

    return jsonify({"results": results})

@app.route('/action', methods=['POST'])
def action_endpoint():
    ensure_fast_model()
    
    try: req = request.get_json(force=True)
    except: return jsonify({"actions": []}), 400
    
    query = req.get('query', "").strip()
    if not query: return jsonify({"actions": []})

    # 1. Shortcuts
    if query.lower() in COMMON_SHORTCUTS:
        url = COMMON_SHORTCUTS[query.lower()]
        act = {
                "type": "link",
                "url": url,
                "title": url.replace("https://", "").replace("www.", "").split('/')[0].title(),
                "description": f"Direct Shortcut"
            }
        return jsonify({"action": act, "actions": [act]})

    # 2. LLM Inference for Action
    # Creating a simplified prompt for the port
    system_prompt = """Output ONLY the matching action(s).
Format:
PERSON:[Name]
PLACE:[Name]
OPEN:https://[URL]
INSTALL:[App Name]
CALC:[Expression]
SEARCH:[Query]
"""
    user_prompt = f"Query: {query}"
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]
    
    try:
        with fast_lock:
            # Gemma 2 instruct check
            out = fast_model.create_chat_completion(
                messages=messages, max_tokens=64, temperature=0.1
            )
            result_text = out['choices'][0]['message']['content'].strip()
            with open("/tmp/llm_output.log", "a") as f:
                f.write(f"Query: {query}\nOutput:\n{result_text}\n{'-'*20}\n")
            
        actions = []
        for line in result_text.split('\n'):
            line = line.strip()
            if not line: continue
            
            if "CALC:" in line:
                expr = line.split("CALC:")[1].strip()
                res = perform_calculation(expr)
                val = res.split("Result: ")[1].strip() if "Result: " in res else res
                actions.append({"type": "calc", "content": val})
            
            elif "SEARCH:" in line:
                q = line.split("SEARCH:")[1].strip()
                # Basic navigation check
                nav = get_navigation_result(q)
                if nav:
                    actions.append({"type": "link", "url": nav['url'], "title": nav['title'], "description": nav['description']})
                else:
                    url = f"https://duckduckgo.com/?q=!ducky+{q}"
                    actions.append({"type": "link", "url": url, "title": f"Search {q}", "description": "Web Search"})
            
            elif "PERSON:" in line:
                name = line.split("PERSON:")[1].strip()
                res = get_person_result(name)
                if res: actions.append(res)
            
            elif "PLACE:" in line:
                name = line.split("PLACE:")[1].strip()
                res = get_place_result(name)
                if res: actions.append(res)

            elif "INSTALL:" in line:
                app = line.split("INSTALL:")[1].strip()
                meta = resolve_app_metadata(app)
                website = meta.get('website') if meta else None
                actions.append({"type": "install", "name": app, "website": website, "content": f"Install {app}"})

            elif "OPEN:" in line:
                url = line.split("OPEN:")[1].strip()
                actions.append({"type": "link", "url": url, "title": "Link", "description": "Open Link"})

        return jsonify({"actions": actions, "action": actions[0] if actions else None})
        
    except Exception as e:
        return jsonify({"actions": [], "error": str(e)})

@app.route('/install_plan', methods=['POST'])
def install_plan_endpoint():
    try: req = request.get_json(force=True)
    except: return jsonify({"error": "Bad JSON"}), 400
    
    app_name = req.get('app_name', '').strip()
    if not app_name: return jsonify({"error": "No app name"}), 400
    
    logging.info(f"Generating Install Plan for: {app_name}")
    
    # 1. APT CHECK (Debian/Ubuntu/Pop)
    try:
        # Search apt cache
        cmd = ["apt-cache", "search", "--names-only", f"^{app_name}$"]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0 and res.stdout.strip():
            # Found exact or close match
            pkg_name = res.stdout.strip().split()[0] # Take first word of first line
            return jsonify({
                "method": "apt",
                "description": f"Found '{pkg_name}' in system repositories",
                "commands": [
                    f"pkexec apt-get install -y {pkg_name}"
                ]
            })
    except Exception as e:
        logging.error(f"Apt check failed: {e}")

    # 2. FLATPAK CHECK
    try:
        # Search flatpak
        cmd = ["flatpak", "search", app_name]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0 and res.stdout.strip():
            # Output format: Name Description ApplicationID Version Branch Remotes
            # We want ApplicationID (3rd column usually, but tricky to parse safely)
            # Let's simple grep for ID
            lines = res.stdout.strip().split('\n')
            if lines:
                parts = lines[0].split('\t')
                if len(parts) > 2:
                    app_id = parts[2].strip()
                else:
                    # Fallback parsing space separated if tabs fail
                    parts = lines[0].split()
                    # finding the reverse domain id usually (com.foo.bar)
                    app_id = next((p for p in parts if '.' in p), None)
                
                if app_id:
                    return jsonify({
                        "method": "flatpak",
                        "description": f"Found '{app_id}' in Flatpak",
                        "commands": [
                            f"flatpak install -y {app_id}"
                        ]
                    })
    except Exception as e:
        logging.error(f"Flatpak check failed: {e}")

    return jsonify({
        "method": "failed", 
        "description": "Could not find package in apt or flatpak.",
        "commands": []
    })

def _startup_sequence():
    time.sleep(2)
    ensure_model_loaded()

if __name__ == '__main__':
    threading.Thread(target=_startup_sequence, daemon=True).start()
    app.run(host='127.0.0.1', port=5500, threaded=True)
