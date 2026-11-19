"""ER diagrams as HTML-table nodes; each line joins an FK row to the PK row it references."""
import subprocess
HDR = '''graph [fontname="Inter", bgcolor="white", pad=0.3, nodesep=0.3, ranksep=0.55, rankdir=LR, splines=spline];
node [fontname="Inter", fontsize=15, fontcolor="#111827", shape=plain];
edge [color="#374151", penwidth=1.3, arrowsize=0.9, dir=both];'''
GROUP = {"core": ("#DBEAFE", "#2563EB"), "money": ("#FEF3C7", "#D97706"), "ai": ("#EDE9FE", "#7C3AED"),
         "people": ("#D1FAE5", "#059669"), "log": ("#F3F4F6", "#6B7280")}

def node(name, group, cols):
    head, border = GROUP[group]
    rows = []
    for c, key in cols:
        tag = {"PK": "<B>PK</B>", "FK": '<FONT COLOR="#1D4ED8"><B>FK</B></FONT>', "UK": "UK", "PK FK": "<B>PK</B> <FONT COLOR='#1D4ED8'><B>FK</B></FONT>", "": ""}[key]
        cname = f"<B>{c}</B>" if "PK" in key else c
        rows.append(f'<TR><TD ALIGN="LEFT" PORT="{c}_w">{tag}</TD><TD ALIGN="LEFT" PORT="{c}_e">{cname}</TD></TR>')
    return (f'{name} [label=<<TABLE BORDER="1" COLOR="{border}" CELLBORDER="0" CELLSPACING="0" CELLPADDING="4" BGCOLOR="white">'
            f'<TR><TD COLSPAN="2" BGCOLOR="{head}"><B>{name}</B></TD></TR>' + "".join(rows) + "</TABLE>>];")

def write(name, tables, rels, extra=""):
    out = ["digraph ER {", HDR] + [node(*t) for t in tables]
    for child, fk, parent, pk, kind in rels:
        tail = "teetee"; head = {"many": "crowodot", "one": "teeodot", "opt": "crowodot"}[kind]
        out.append(f'{parent}:{pk}_e:e -> {child}:{fk}_w:w [arrowtail={tail}, arrowhead={head}];')
    out += [extra, "}"]
    open(f"{name}.dot", "w").write("\n".join(out))
    r = subprocess.run(["dot", "-Tpng", "-Gdpi=200", f"{name}.dot", "-o", f"{name}.png"], capture_output=True, text=True)
    if r.returncode: print("FAIL", name, r.stderr[:300])

emp = ("employees", "people", [("employee_id","PK"),("full_name",""),("email","UK"),("password_hash",""),("department",""),("role",""),("manager_id","FK")])
trip = ("travel_requests", "core", [("trip_id","PK"),("trip_code","UK"),("employee_id","FK"),("destination",""),("start_date",""),("end_date",""),("purpose",""),("approval_status",""),("trip_state",""),("completion_type",""),("completed_by","FK"),("created_at","")])
tapp = ("trip_approvals", "core", [("approval_id","PK"),("trip_id","FK"),("reviewer_id","FK"),("decision",""),("review_comment",""),("decided_at","")])
tick = ("expense_tickets", "money", [("ticket_id","PK"),("ticket_code","UK"),("trip_id","FK"),("employee_id","FK"),("replacement_of_ticket_id","FK"),("status",""),("routing",""),("total_amount","")])
exp = ("expenses", "money", [("expense_id","PK"),("expense_code","UK"),("ticket_id","FK"),("trip_id","FK"),("evidence_id","FK"),("expense_type",""),("amount",""),("expense_date",""),("invoice_number",""),("status","")])
evd = ("expense_evidence", "money", [("evidence_id","PK"),("evidence_code","UK"),("employee_id","FK"),("mime_type",""),("size_bytes",""),("sha256",""),("uploaded_at","")])
evf = ("evidence_files", "money", [("evidence_id","PK FK"),("content","")])
flag = ("policy_flags", "money", [("flag_id","PK"),("expense_id","FK"),("rule_code",""),("message","")])
kapp = ("ticket_approvals", "money", [("approval_id","PK"),("ticket_id","FK"),("reviewer_type",""),("reviewer_id","FK"),("decision",""),("rejection_reason",""),("review_comment",""),("decided_at","")])

write("07_er_trips", [emp, trip, tapp], [
  ("travel_requests","employee_id","employees","employee_id","many"),
  ("travel_requests","completed_by","employees","employee_id","opt"),
  ("trip_approvals","trip_id","travel_requests","trip_id","one"),
  ("trip_approvals","reviewer_id","employees","employee_id","many"),
])
tripm = ("travel_requests", "core", [("trip_id","PK"),("trip_code","UK"),("approval_status",""),("trip_state","")])
write("08_er_expenses", [tripm, tick, exp, flag, kapp, evd, evf], [
  ("expense_tickets","trip_id","travel_requests","trip_id","many"),
  ("expenses","ticket_id","expense_tickets","ticket_id","many"),
  ("expenses","trip_id","travel_requests","trip_id","many"),
  ("expenses","evidence_id","expense_evidence","evidence_id","one"),
  ("evidence_files","evidence_id","expense_evidence","evidence_id","one"),
  ("policy_flags","expense_id","expenses","expense_id","many"),
  ("ticket_approvals","ticket_id","expense_tickets","ticket_id","one"),
], '{rank=same; expense_tickets; expense_evidence}')

empm = ("employees", "people", [("employee_id","PK"),("full_name","")])
ses = ("chat_sessions", "ai", [("session_id","PK"),("employee_id","FK"),("status",""),("close_reason",""),("summary",""),("summarized_upto_turn",""),("started_at",""),("last_activity_at",""),("closed_at","")])
conv = ("chat_conversations", "ai", [("conversation_id","PK"),("session_id","FK"),("turn_number",""),("intent",""),("status",""),("guardrail_status",""),("correlation_id",""),("latency_ms","")])
msg = ("chat_messages", "ai", [("message_id","PK"),("session_id","FK"),("conversation_id","FK"),("sequence_no",""),("message_type",""),("content",""),("tool_name",""),("tool_call_id",""),("tool_args",""),("metadata","")])
aic = ("ai_call_logs", "log", [("log_id","PK"),("session_id","FK"),("conversation_id","FK"),("feature",""),("model_name",""),("prompt_version",""),("status",""),("latency_ms",""),("correlation_id","")])
rag = ("rag_call_logs", "log", [("rag_call_id","PK"),("session_id","FK"),("conversation_id","FK"),("retrieved_ref_ids",""),("retrieval_scores",""),("citations_used",""),("status",""),("latency_ms","")])
wtl = ("weather_tool_logs", "log", [("weather_call_id","PK"),("session_id","FK"),("conversation_id","FK"),("tool_call_id",""),("destination_query",""),("start_date",""),("end_date",""),("result_status",""),("error_code",""),("cache_hit","")])
err = ("error_logs", "log", [("error_id","PK"),("occurred_at",""),("category",""),("error_code",""),("request_id",""),("correlation_id",""),("session_id",""),("conversation_id",""),("http_status","")])
pol = ("policy_chunks", "ai", [("chunk_id","PK"),("ref_id",""),("section_title",""),("content",""),("embedding",""),("content_hash","UK")])
write("11_er_chat", [empm, ses, conv, msg, pol], [
  ("chat_sessions","employee_id","employees","employee_id","many"),
  ("chat_conversations","session_id","chat_sessions","session_id","many"),
  ("chat_messages","conversation_id","chat_conversations","conversation_id","many"),
  ("chat_messages","session_id","chat_sessions","session_id","many"),
], '{rank=same; policy_chunks; employees}')
convm = ("chat_conversations", "ai", [("conversation_id","PK"),("session_id","FK"),("turn_number",""),("correlation_id","")])
write("11b_er_logs", [convm, aic, rag, wtl, err], [
  ("ai_call_logs","conversation_id","chat_conversations","conversation_id","opt"),
  ("rag_call_logs","conversation_id","chat_conversations","conversation_id","many"),
  ("weather_tool_logs","conversation_id","chat_conversations","conversation_id","many"),
], '{rank=same; error_logs; chat_conversations}')
