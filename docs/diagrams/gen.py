"""Writes every flow diagram as Graphviz DOT with one shared clean style, then renders PNG."""
import subprocess
HDR = '''graph [fontname="Inter", fontsize=15, fontcolor="#111827", bgcolor="white", pad=0.3, nodesep=0.45, ranksep=0.5];
node  [fontname="Inter", fontsize=14, fontcolor="#111827", shape=box, style="rounded,filled", fillcolor="#F9FAFB", color="#6B7280", penwidth=1.6, margin="0.22,0.12"];
edge  [fontname="Inter", fontsize=12, fontcolor="#111827", color="#374151", penwidth=1.4, arrowsize=0.8];
'''
EMP = 'fillcolor="#EFF6FF", color="#2563EB"'   # employee
SYS = 'fillcolor="#FFFBEB", color="#D97706"'   # system rule
MGR = 'fillcolor="#ECFDF5", color="#059669"'   # manager / approved
ERR = 'fillcolor="#FEF2F2", color="#DC2626"'   # error / external
AI  = 'fillcolor="#F5F3FF", color="#7C3AED"'   # AI / Vera
NEU = 'fillcolor="#F9FAFB", color="#6B7280"'
DIA = 'shape=diamond, style=filled, fillcolor="white", margin="0.05,0.05"'
D = {}

D["01_trip_lifecycle"] = f'''rankdir=TB; ranksep=0.7; nodesep=0.9;
st [shape=circle, label="", width=0.25, style=filled, fillcolor="#111827", color="#111827"];
ip [label=<<B>In Progress</B><BR/><FONT POINT-SIZE="11">trip ID created, waiting for manager</FONT>>, {EMP}];
rj [label=<<B>Rejected</B><BR/><FONT POINT-SIZE="11">final, read-only</FONT>>, {ERR}];
ac [label=<<B>Approved - Active</B><BR/><FONT POINT-SIZE="11">tickets and expenses allowed</FONT>>, {MGR}, penwidth=2.4];
co [label=<<B>Approved - Completed</B><BR/><FONT POINT-SIZE="11">no new tickets or expenses</FONT>>, {NEU}];
st -> ip [label="  employee submits\\n  (start within 1 year)"];
ip -> ip [label=" employee edits"];
ip -> rj [label="  manager rejects\\n  (review comment)"];
ip -> ac [label="  manager approves"];
ac -> ac [label=" raise tickets"];
ac -> co [label="  manager marks complete (on/after end date)\\n  or system: start date + 90 days"];
{{rank=same; rj; ac}}'''

D["02_ticket_routing"] = f'''rankdir=TB; ranksep=0.42; nodesep=0.6;
a [label="Employee uploads one receipt photo per line\\n(each gets an EVD id), then submits", {EMP}];
b [{DIA}, label="Valid lines?\\nphoto on every line,\\ndate >= trip created,\\nnot future, amount ok"];
b1 [label="422 error under the field\\nnothing saved", {ERR}];
c [{DIA}, label="Trip\\nApproved - Active?"];
c1 [label="409 TRIP_NOT_ACTIVE", {ERR}];
p [shape=plain, label=<<TABLE BORDER="1" COLOR="#D97706" CELLBORDER="0" CELLSPACING="0" CELLPADDING="7" BGCOLOR="#FFFBEB" STYLE="rounded">
  <TR><TD><B>Policy engine checks each line</B></TD></TR>
  <TR><TD ALIGN="LEFT">Amount over category limit</TD></TR>
  <TR><TD ALIGN="LEFT">Same photo or invoice no. already claimed</TD></TR></TABLE>>];
d [{DIA}, label="Any flag?"];
e [label=<<B>Auto-approved</B><BR/><FONT POINT-SIZE="11">reviewer = SYSTEM, final</FONT>>, {MGR}];
f [label=<<B>Pending</B><BR/><FONT POINT-SIZE="11">sent to manager</FONT>>, {SYS}];
g [label="Manager reviews lines + photos\\napproves, or rejects with\\nreason + review comment", {MGR}];
h [label=<<B>Approved</B><BR/><FONT POINT-SIZE="11">final, comment optional</FONT>>, {MGR}];
r [label=<<B>Rejected</B><BR/><FONT POINT-SIZE="11">final and read-only</FONT>>, {ERR}];
n [label="Employee creates a NEW ticket, same trip_id:\\nnew ticket id, new expense ids,\\nphotos uploaded again (new evidence ids)", {EMP}];
a -> b; b -> b1 [label=" no"]; b -> c [label=" yes"]; c -> c1 [label=" no"]; c -> p [label=" yes"]; p -> d;
d -> e [label=" no"]; d -> f [label=" yes"]; f -> g; g -> h [label=" approve"]; g -> r [label=" reject"];
r -> n [label="  if trip still Active"]; n -> b [style=dashed, constraint=false, label=" full validation again"];
{{rank=same; b; b1}} {{rank=same; c; c1}} {{rank=same; e; f}} {{rank=same; h; r}}'''

D["03_journey"] = f'''rankdir=TB; ranksep=0.38;
node [width=3.2];
a [label="1. Employee signs in (JWT)\\nand creates a trip request", {EMP}];
b [label="2. Manager reviews the request", {MGR}];
r [label="Rejected (final)", {ERR}, width=1.8];
c [label=<<B>3. Trip is Approved - Active</B>>, {MGR}, penwidth=2.2];
v [label="4. Optional: asks Vera about the\\nexpense policy or the weather\\n(types destination + dates)", {AI}];
e [label="5. Employee raises a ticket in\\nExpense Management (photo per line)", {EMP}];
f [label="6. Policy engine checks every line", {SYS}];
g [label="Auto-approved", {SYS}, width=1.8];
h [label="7. Manager reviews photos,\\napproves or rejects + comment", {MGR}, width=2.6];
n [label="Rejected: employee raises a\\nnew ticket on the same trip", {EMP}, width=2.6];
i [label="8. Trip completed: manager after end date\\nor system at start date + 90 days", {MGR}];
j [label="9. Manager views spending summary", {MGR}];
a -> b; b -> r [label=" reject"]; b -> c [label=" approve"]; c -> v [style=dashed]; c -> e; v -> e [style=invis];
e -> f; f -> g [label=" no flags"]; f -> h [label=" any flag"]; h -> n [label=" reject"]; n -> f [style=dashed, constraint=false];
g -> i; h -> i [label=" approve"]; i -> j;
{{rank=same; b; r}} {{rank=same; g; h}}
key [shape=plain, width=0, label=<<TABLE BORDER="1" COLOR="#D1D5DB" CELLBORDER="1" CELLSPACING="4" CELLPADDING="5" BGCOLOR="white">
  <TR><TD BORDER="0"><B>Colour key</B></TD></TR>
  <TR><TD BGCOLOR="#EFF6FF" COLOR="#2563EB">Employee</TD></TR><TR><TD BGCOLOR="#FFFBEB" COLOR="#D97706">System rule</TD></TR>
  <TR><TD BGCOLOR="#ECFDF5" COLOR="#059669">Manager</TD></TR><TR><TD BGCOLOR="#F5F3FF" COLOR="#7C3AED">Vera (AI)</TD></TR></TABLE>>];
{{rank=same; a; key}}'''

D["04_architecture"] = f'''rankdir=TB; compound=true; ranksep=0.55;
subgraph cluster_ui {{ label=<<B>React</B>  (one app, two views chosen by the JWT role)>; style="rounded,filled"; fillcolor="#EFF6FF"; color="#2563EB"; margin=12;
  u1 [label="Employee view\\nMy Trips, Trip Detail,\\nExpense Management", fillcolor="white", color="#2563EB"];
  u2 [label="Vera chat\\n(My Trips and Expense\\nManagement only)", fillcolor="white", color="#7C3AED"];
  u3 [label="Manager view\\nApprovals, Ticket review,\\nSpending Summary", fillcolor="white", color="#059669"];
  {{rank=same; u1 -> u2 -> u3 [style=invis];}} }}
subgraph cluster_api {{ label=<<B>FastAPI</B>  (verifies JWT, role, ownership on every request)<BR/><FONT COLOR="#DC2626" POINT-SIZE="12">Vera has no path to business repositories</FONT>>; style="rounded,filled"; fillcolor="#F9FAFB"; color="#6B7280"; margin=12;
  b1 [label=<<B>Business API</B><BR/><FONT POINT-SIZE="12">auth, trips, evidence, tickets,<BR/>decisions, reports</FONT>>, fillcolor="white"];
  c1 [label=<<B>Chat API</B><BR/><FONT POINT-SIZE="12">Employee role only</FONT>>, {AI}];
  b2 [label="Business services\\n+ policy engine", fillcolor="white"];
  c2 [label="Vera chat service\\n(isolated)", {AI}];
  b3 [label="Business\\nrepositories", fillcolor="white"];
  c3 [label="Chat repo, RAG,\\nWeatherService", {AI}];
  b1 -> b2 -> b3; c1 -> c2 -> c3;
  b2 -> c3 [style=invis]; }}
db [shape=cylinder, label=<<B>PostgreSQL (local)</B><BR/><FONT POINT-SIZE="12">business, evidence, chat, policy chunks, logs<BR/>administered with pgAdmin</FONT>>, {MGR}];
om [label="Open-Meteo\\nweather API", {ERR}];
ai [label="Hosted LLM\\nOpenRouter Nemotron", {ERR}];
u1 -> b1 [label=" Bearer JWT"]; u3 -> b1; u2 -> c1 [label=" Bearer JWT"];
b3 -> db; c3 -> db; c3 -> om; c2 -> ai;
{{rank=same; om; ai}}'''

D["05_backend_deps"] = f'''rankdir=TB; ranksep=0.42;
m [label=<<B>main.py</B><BR/><FONT POINT-SIZE="12">middleware: request + correlation id, error handler</FONT>>, width=4];
subgraph cluster_b {{ label=<<B>Business side</B>>; style="rounded"; color="#9CA3AF"; margin=10;
  br [label=<<B>routers/</B><BR/><FONT POINT-SIZE="11">auth, trips, evidence, tickets,<BR/>expenses, reports, policy, health</FONT>>, {EMP}];
  bs [label=<<B>services/</B><BR/><FONT POINT-SIZE="11">auth, trip, evidence, ticket,<BR/>approval, report, scheduler jobs</FONT>>];
  pe [label="policy_engine\\n(pure rules)", {SYS}];
  bp [label=<<B>business repositories</B><BR/><FONT POINT-SIZE="11">employee, trip, ticket, expense,<BR/>evidence, approval, report</FONT>>, {MGR}];
  br -> bs -> pe; bs -> bp; }}
subgraph cluster_c {{ label=<<B>Vera side (isolated)</B>>; style="rounded"; color="#7C3AED"; margin=10;
  cr [label=<<B>routers/chat.py</B><BR/><FONT POINT-SIZE="11">Employee role only</FONT>>, {AI}];
  cs [label=<<B>chat/</B><BR/><FONT POINT-SIZE="11">session manager, intent router,<BR/>guardrails, context, tools</FONT>>, {AI}];
  rg [label="rag/\\nretriever", {AI}]; ws [label="services/\\nweather_service", {AI}]; ll [label="ai/llm_client", {AI}];
  cp [label=<<B>chat_repo + log repos</B><BR/><FONT POINT-SIZE="11">chat_*, rag/weather/ai logs</FONT>>, {MGR}];
  cr -> cs; cs -> rg; cs -> ws; cs -> ll; cs -> cp; rg -> cp [style=invis]; }}
db [label=<<B>core/database.py</B> to local PostgreSQL>, width=4];
m -> br; m -> cr; bp -> db; cp -> db; rg -> db;
bs -> cs [style=invis];
cs -> bp [style=dashed, color="#DC2626", fontcolor="#DC2626", label=" forbidden\\n (import test fails)", constraint=false, arrowhead=tee];'''

D["06_frontend"] = f'''rankdir=TB; ranksep=0.42; compound=true; nodesep=0.3;
lg [label=<<B>Login</B>  e-mail + password -&gt; JWT>, width=4];
ac [label=<<B>AuthContext</B>  token + role in sessionStorage>, width=4];
subgraph cluster_e {{ label=<<B>EmployeeRoute</B> (role EMPLOYEE)>; style="rounded,filled"; fillcolor="#EFF6FF"; color="#2563EB"; margin=10;
  node [fillcolor="white", color="#2563EB", fontsize=13];
  e1 [label="My Trips\\n+ Vera icon"]; e2 [label="Create Trip"]; e3 [label="Trip Detail\\n(no Vera)"];
  e4 [label="Expense Management\\n+ Vera icon"]; e5 [label="Raise Ticket\\n(no Vera)"]; e6 [label="Ticket Detail\\n(no Vera)"];
  {{rank=same; e1 -> e2 -> e3 [style=invis];}} {{rank=same; e4 -> e5 -> e6 [style=invis];}} e1 -> e4 [style=invis]; }}
subgraph cluster_m {{ label=<<B>ManagerRoute</B> (role MANAGER, no Vera)>; style="rounded,filled"; fillcolor="#ECFDF5"; color="#059669"; margin=10;
  node [fillcolor="white", color="#059669", fontsize=13];
  m1 [label="Approvals\\n(3 tabs)"]; m2 [label="Trip review"]; m3 [label="Ticket review\\ncomment + decision"]; m4 [label="Spending\\nSummary"];
  {{rank=same; m1 -> m2 [style=invis];}} {{rank=same; m3 -> m4 [style=invis];}} m1 -> m3 [style=invis]; }}
api [label=<<B>src/api/client.js</B>  base URL, Bearer JWT, 401 -&gt; login, error envelope>, width=5.5];
be [label="FastAPI re-checks JWT signature, expiry, role, ownership", fillcolor="#FEF2F2", color="#DC2626", width=5.5];
lg -> ac; ac -> e2 [lhead=cluster_e]; ac -> m2 [lhead=cluster_m];
e5 -> api [ltail=cluster_e]; m2 -> api [ltail=cluster_m]; api -> be;'''

D["09_weather_tool"] = f'''rankdir=TB; ranksep=0.38; nodesep=0.3;
node [width=3.0];
a [label=<<B>Employee message</B><BR/><FONT POINT-SIZE="12">"Bengaluru, 25 to 28 Nov - what to pack?"</FONT>>, {EMP}];
b [{DIA}, label="Destination, start\\nand end all given?", width=2.6];
q [label="Vera asks for the missing item\\n(no tool call)", {AI}, width=2.6];
c [label="get_weather_forecast(destination, start, end)\\nvalidate dates (<= 30 days)", {AI}];
g [label="Geocode with Open-Meteo\\n(not found / ambiguous -> ask)", {NEU}];
h [label="Split dates: covered = today .. today + 15\\nothers = uncovered", {NEU}];
k [{DIA}, label="Any covered\\ndate?", width=2.2];
oo [label="FORECAST_OUT_OF_RANGE\\n'Forecast not available', no values", {SYS}, width=2.8];
f [label="Forecast call for covered dates only\\nvalues copied exactly; log the call", {NEU}];
v [label="Vera answer: summary + checklist + limitations\\nnumbers checked against tool data", {MGR}];
x [label="Timeout / 5xx / 429 / bad JSON:\\nsafe message + Retry, error logged,\\nno invented forecast", {ERR}, width=3.0];
a -> b; b -> q [label=" no"]; b -> c [label=" yes"]; c -> g -> h -> k; k -> oo [label=" no"]; k -> f [label=" yes"]; f -> v; oo -> v [style=dashed];
g -> x [style=dotted]; f -> x [style=dotted];
{{rank=same; b; q}} {{rank=same; k; oo}} {{rank=same; f; x}}'''

D["10_session"] = f'''rankdir=TB; ranksep=0.7; nodesep=1.0;
st [shape=circle, label="", width=0.25, style=filled, fillcolor="#111827", color="#111827"];
a [label=<<B>ACTIVE</B><BR/><FONT POINT-SIZE="11">memory = this session only</FONT>>, {MGR}, penwidth=2.4];
c [label=<<B>CLOSED</B><BR/><FONT POINT-SIZE="11">X clicked, or replaced</FONT>>];
x [label=<<B>EXPIRED</B><BR/><FONT POINT-SIZE="11">60 minutes with no message</FONT>>, {ERR}];
h [label=<<B>Kept in PostgreSQL</B><BR/><FONT POINT-SIZE="11">readable in Past chats,<BR/>never loaded into a new chat</FONT>>, {NEU}];
st -> a [label="  icon clicked:\\n  new session_id"];
a -> a [label=" each message =\\n new conversation_id"];
a -> c [label=" close"]; a -> x [label=" idle"]; c -> h; x -> h;
{{rank=same; c; x}}'''

D["12_rag"] = f'''rankdir=LR; ranksep=0.45; nodesep=0.35;
subgraph cluster_i {{ label=<<B>Setup: load the policy once</B>>; style="rounded"; color="#9CA3AF"; margin=12;
  a [label="Policy\\n.txt file"]; b [label="Split by\\nrule ID"]; c [label="Embed\\n(MiniLM)"]; e [shape=cylinder, label="policy_chunks\\nREAL[] vectors", {MGR}];
  a -> b -> c -> e; }}
subgraph cluster_q {{ label=<<B>Only when the intent is POLICY</B>>; style="rounded"; color="#9CA3AF"; margin=12;
  q [label="Policy\\nquestion", {EMP}]; t [label="search_expense_\\npolicy tool", {AI}]; s [label="Top 4 by cosine\\n(>= 0.35)"]; g [label="Answer with\\n[POL-x.y] citations", {AI}];
  q -> t -> s -> g; }}
e -> s [style=dashed, constraint=false];
a -> q [style=invis];'''

D["08b_replacement"] = f'''rankdir=LR; ranksep=0.6; nodesep=0.35; compound=true;
t [label=<<B>TRP-00002</B><BR/><FONT POINT-SIZE="12">same trip_id, Approved - Active</FONT>>, {EMP}];
subgraph cluster_old {{ label=<<B>Rejected ticket</B> (read-only, kept for audit)>; style="rounded,filled"; fillcolor="#FEF2F2"; color="#DC2626"; margin=12;
  o1 [label=<<B>TKT-00004</B><BR/><FONT POINT-SIZE="11">status REJECTED</FONT>>, fillcolor="white", color="#DC2626"];
  o2 [label=<<B>EXP-00007</B><BR/><FONT POINT-SIZE="11">AIRFARE 4,200</FONT>>, fillcolor="white", color="#DC2626"];
  o3 [label=<<B>EVD-00007</B><BR/><FONT POINT-SIZE="11">blurred photo</FONT>>, fillcolor="white", color="#DC2626"];
  o4 [label=<<B>Manager decision</B><BR/><FONT POINT-SIZE="11">INSUFFICIENT_EVIDENCE<BR/>"Photo is blurred..."</FONT>>, fillcolor="white", color="#DC2626"];
  o1 -> o2 -> o3; o1 -> o4; }}
subgraph cluster_new {{ label=<<B>Replacement ticket</B> (all new ids, full validation)>; style="rounded,filled"; fillcolor="#ECFDF5"; color="#059669"; margin=12;
  n1 [label=<<B>TKT-00006</B><BR/><FONT POINT-SIZE="11">replacement_of_ticket_id = 4</FONT>>, fillcolor="white", color="#059669"];
  n2 [label=<<B>EXP-00009</B><BR/><FONT POINT-SIZE="11">AIRFARE 4,200</FONT>>, fillcolor="white", color="#059669"];
  n3 [label=<<B>EVD-00009</B><BR/><FONT POINT-SIZE="11">new clear photo upload</FONT>>, fillcolor="white", color="#059669"];
  n1 -> n2 -> n3; }}
t -> o1 [lhead=cluster_old]; t -> n1 [lhead=cluster_new];
n1 -> o1 [style=dashed, constraint=false, color="#6B7280"];'''

def write_render():
    for name, body in D.items():
        open(f"{name}.dot", "w").write("digraph G {\n" + HDR + body + "\n}\n")
        r = subprocess.run(["dot", "-Tpng", "-Gdpi=200", f"{name}.dot", "-o", f"{name}.png"], capture_output=True, text=True)
        if r.returncode: print("FAIL", name, r.stderr[:300])
write_render()
