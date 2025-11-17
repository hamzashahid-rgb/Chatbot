from flask import Flask, request, jsonify, render_template_string, session
import os
from dotenv import load_dotenv

# --- Load env ---
load_dotenv()
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise RuntimeError("Set OPENAI_API_KEY in your environment or .env file.")


from openai import OpenAI
client = OpenAI(api_key=OPENAI_API_KEY)

# --- Flask app ---
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "change-me-for-prod")


HTML = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>AI Chatbot (Flask)</title>
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <style>
    body { font-family: Inter, system-ui, -apple-system, Arial; max-width:900px; margin:28px auto; }
    h1 { font-size: 22px; }
    #chat { border:1px solid #e6e6e6; padding: 12px; height: 60vh; overflow:auto; background:#fafafa; }
    .row { display:flex; gap:8px; margin:8px 0; }
    .bubble { padding:10px 12px; border-radius:10px; max-width:80%; }
    .user { justify-content:flex-end; }
    .user .bubble { background:#0b5cff; color:white; border-bottom-right-radius:2px; }
    .bot .bubble { background:white; color:#111; border:1px solid #eee; }
    #controls{ margin-top:12px; display:flex; gap:8px }
    input[type=text]{ flex:1; padding:10px; font-size:14px }
    button{ padding:10px 14px }
    #status{ margin-left:8px; color:#666 }
  </style>
</head>
<body>
  <h1>AI Chatbot</h1>
  <div id="chat"></div>
  <div id="controls">
    <input id="prompt" type="text" placeholder="Type a message and press Enter" />
    <button id="send">Send</button>
    <button id="clear">Clear</button>
    <span id="status"></span>
  </div>

<script>
const chatEl = document.getElementById('chat');
const promptEl = document.getElementById('prompt');
const statusEl = document.getElementById('status');

function appendMessage(role, text){
  const row = document.createElement('div');
  row.className = 'row ' + (role==='user' ? 'user' : 'bot');
  const bub = document.createElement('div');
  bub.className = 'bubble';
  bub.textContent = text;
  row.appendChild(bub);
  chatEl.appendChild(row);
  chatEl.scrollTop = chatEl.scrollHeight;
}

async function sendMessage(text){
  if(!text) return;
  appendMessage('user', text);
  promptEl.value='';
  statusEl.textContent='Thinking...';
  try{
    const res = await fetch('/chat', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({message: text})
    });
    const j = await res.json();
    if(j.error){
      appendMessage('bot', 'Error: ' + j.error);
    } else {
      appendMessage('bot', j.reply);
    }
  } catch(e){
    appendMessage('bot', 'Network error');
  } finally{
    statusEl.textContent='';
  }
}

promptEl.addEventListener('keydown', (e)=>{ if(e.key==='Enter'){ sendMessage(promptEl.value.trim()); }});
document.getElementById('send').addEventListener('click', ()=> sendMessage(promptEl.value.trim()));
document.getElementById('clear').addEventListener('click', async ()=>{
  const r = await fetch('/clear', {method:'POST'});
  if(r.ok){ chatEl.innerHTML=''; }
});

// Load existing session history when page opens
async function loadHistory(){
  const r = await fetch('/history');
  const j = await r.json();
  if(j.history && j.history.length){
    for(const m of j.history){ appendMessage(m.role, m.content); }
  }
}
loadHistory();
</script>
</body>
</html>
"""

# --- Helpers ---
SYSTEM_PROMPT = "You are a helpful, friendly assistant. Keep answers concise unless user asks for detail."

def get_history():
    # store a list of dicts: {'role': 'user'/'assistant'/'system', 'content': '...'}
    return session.setdefault('history', [{'role':'system','content':SYSTEM_PROMPT}])

def append_to_history(role, content):
    h = get_history()
    h.append({'role':role, 'content':content})
    # keep last ~20 messages to limit token usage
    if len(h) > 40:
        # keep the system prompt then the last 39 messages
        h[:] = [h[0]] + h[-39:]
    session['history'] = h

# --- Routes ---
@app.route('/')
def index():
    return render_template_string(HTML)

@app.route('/history')
def history():
    return jsonify({'history': get_history()})

@app.route('/clear', methods=['POST'])
def clear():
    session.pop('history', None)
    return ('', 204)

@app.route('/chat', methods=['POST'])
def chat():
    data = request.get_json(force=True)
    user_message = data.get('message','').strip()
    if not user_message:
        return jsonify({'error':'empty message'}), 400

    append_to_history('user', user_message)

    # Call OpenAI chat completion
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",  # change model if you prefer
            messages=session['history'],
            max_tokens=512,
            temperature=0.2,
        )
        assistant_msg = resp.choices[0].message.content
    except Exception as e:
        # return friendly error, but avoid leaking sensitive internals
        return jsonify({'error': str(e)}), 500

    append_to_history('assistant', assistant_msg)
    return jsonify({'reply': assistant_msg})

if __name__ == '__main__':
    # For local dev only. In production use a WSGI server like gunicorn
    app.run(host='127.0.0.1', port=5000, debug=True)