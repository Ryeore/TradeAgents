"""Compare old vs new WSE screen after P/E fallback."""
import json

def load(path):
    d = open(path, 'rb').read()
    t = d.decode('utf-16') if d[:2] == b'\xff\xfe' else d.decode('utf-8-sig')
    return json.loads(t)

s1 = load('screen_wse_full.json')
suc1 = [r for r in s1.get('ranked', []) if not r.get('error') and r.get('screen_score') is not None]
pe_missing_old = [r for r in suc1 if r.get('signals', {}).get('pe_forward') is None]

s2 = load('screen_wse_v2.json')
suc2 = [r for r in s2.get('ranked', []) if not r.get('error') and r.get('screen_score') is not None]
pe_missing_new = [r for r in suc2 if r.get('signals', {}).get('pe_forward') is None]

print('=== PE_FORWARD COVERAGE ===')
print('Old missing pe_forward:', len(pe_missing_old), '/', len(suc1))
print('New missing pe_forward:', len(pe_missing_new), '/', len(suc2))
print()

# Check how many were backfilled
old_names = {r['symbol']: r for r in pe_missing_old}
new_map = {r['symbol']: r for r in suc2}

print('=== BACKFILLED STOCKS (confidence before/after) ===')
improvements = []
for sym, old_r in sorted(old_names.items()):
    new_r = new_map.get(sym)
    if new_r:
        oc = old_r.get('confidence_score', 0)
        nc = new_r.get('confidence_score', 0)
        oa = old_r.get('screen_score') or 0
        na = new_r.get('screen_score') or 0
        src = new_r.get('biznesradar_sourced', [])
        backfilled = 'pe_trailing_as_forward' in src
        improvements.append((nc - oc, sym, oc, nc, oa, na, backfilled))

improvements.sort(reverse=True)
print(f'  {"Sym":10s} {"OldConf":>7s} {"NewConf":>7s} {"Gain":>6s}  {"OldAdj":>7s} {"NewAdj":>7s}  BR')
for imp, sym, oc, nc, oa, na, br in improvements[:20]:
    print(f'  {sym:10s} {oc:7.1f}% {nc:7.1f}% {imp:+6.1f}%  {oa:7.1f} {na:7.1f}  {"Y" if br else "N"}')

gains = [i[0] for i in improvements]
print()
print(f'Average confidence gain: {sum(gains)/len(gains):.1f}%')
print(f'Max confidence gain: {max(gains):.1f}%')
adj_gains = [i[5] - i[4] for i in improvements]
print(f'Average adj score change: {sum(adj_gains)/len(adj_gains):.1f}')
backfilled_count = sum(1 for i in improvements if i[6])
print(f'Actually backfilled by biznesradar: {backfilled_count}/{len(improvements)}')

# Overall
confs1 = [r.get('confidence_score', 0) for r in suc1]
confs2 = [r.get('confidence_score', 0) for r in suc2]
print()
print('=== OVERALL ===')
print('Old avg conf:', round(sum(confs1)/len(confs1), 1))
print('New avg conf:', round(sum(confs2)/len(confs2), 1))
print('Old min conf:', round(min(confs1), 1))
print('New min conf:', round(min(confs2), 1))
print('Old conf < 50:', sum(1 for c in confs1 if c < 50))
print('New conf < 50:', sum(1 for c in confs2 if c < 50))
print('Old conf < 30:', sum(1 for c in confs1 if c < 30))
print('New conf < 30:', sum(1 for c in confs2 if c < 30))

# Sector impact
from collections import Counter
print()
print('=== SECTOR IMPACT ===')
old_sector_conf = {}
new_sector_conf = {}
for r in suc1:
    sec = r.get('sector', '?')
    if sec not in old_sector_conf: old_sector_conf[sec] = []
    old_sector_conf[sec].append(r.get('confidence_score', 0))
for r in suc2:
    sec = r.get('sector', '?')
    if sec not in new_sector_conf: new_sector_conf[sec] = []
    new_sector_conf[sec].append(r.get('confidence_score', 0))

for sec in sorted(old_sector_conf):
    old_avg = sum(old_sector_conf[sec]) / len(old_sector_conf[sec])
    new_avg = sum(new_sector_conf.get(sec, [0])) / len(new_sector_conf.get(sec, [1]))
    print(f'  {sec:30s} old={old_avg:.1f}% new={new_avg:.1f}% change={new_avg-old_avg:+.1f}%')