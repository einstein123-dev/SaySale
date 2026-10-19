"""Shared presentation helpers. Escape all user-controlled HTML."""
import re
from html import escape
import pandas as pd
import streamlit as st


def _cell(value):
    """Escape a value for inline HTML and collapse whitespace/newlines.

    A blank line inside an HTML block ends the block in Streamlit's markdown
    renderer, so multi-line notes/names would otherwise break the layout.
    """
    return escape(' '.join(str(value).split()))


def sales_over_time_frame(rows, timezone='UTC', currency='USD', language='en', days=30, today=None):
    from datetime import datetime, time as datetime_time, timedelta, timezone as utc_timezone
    from zoneinfo import ZoneInfo
    from i18n import tr
    from intl import major_units

    if not isinstance(days, int) or isinstance(days, bool) or days < 1:
        raise ValueError('Chart range must be a positive whole number of days.')
    rows=[dict(row) for row in rows]
    shop_timezone=ZoneInfo(timezone)
    end_day=today or datetime.now(shop_timezone).date()
    start_day=end_day-timedelta(days=days-1)
    daily_minor={start_day+timedelta(days=offset):0 for offset in range(days)}

    voided_ids=set()
    for row in rows:
        note=str(row.get('note') or '')
        prefix='Void of '
        if row.get('type')=='void' and note.startswith(prefix) and 'Reason:' in note:
            target=note[len(prefix):].split('Reason:',1)[0].strip()
            target_parts=target.rsplit(' ',1)
            voided_ids.add(target_parts[0] if len(target_parts)>1 else target)

    for row in rows:
        if row.get('type')!='sale' or row.get('id') in voided_ids or row.get('amount_minor') is None:
            continue
        try:
            timestamp=datetime.fromisoformat(str(row['created_at']).replace('Z','+00:00'))
        except (KeyError,TypeError,ValueError):
            continue
        if timestamp.tzinfo is None:
            timestamp=timestamp.replace(tzinfo=utc_timezone.utc)
        sale_day=timestamp.astimezone(shop_timezone).date()
        if sale_day in daily_minor:
            daily_minor[sale_day]+=row['amount_minor']

    index=pd.DatetimeIndex([datetime.combine(day,datetime_time.min) for day in daily_minor],name=tr('Date',language))
    values=[float(major_units(amount,currency)) for amount in daily_minor.values()]
    return pd.DataFrame({tr('Sales',language):values},index=index)

STYLE = '''<style>
@keyframes rise{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:translateY(0)}}
@keyframes pulse{0%,100%{box-shadow:0 0 0 0 #69b89335}50%{box-shadow:0 0 0 6px #69b89300}}
@keyframes soft-in{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:translateY(0)}}
@keyframes glow-in{from{opacity:.55;box-shadow:0 0 0 0 #bcd89b00}to{opacity:1;box-shadow:0 0 0 8px #bcd89b00}}
@keyframes logo-bounce{0%,20%,50%,80%,100%{transform:translateY(0)}40%{transform:translateY(-6px)}60%{transform:translateY(-3px)}}
@keyframes float-particle{0%,100%{transform:translate3d(0,8vh,0) scale(.8);opacity:0}15%{opacity:.55}50%{transform:translate3d(5vw,-45vh,0) scale(1);opacity:.28}85%{opacity:.5}}
.particle-field{position:fixed;inset:0;overflow:hidden;pointer-events:none;z-index:0}
.particle{position:absolute;bottom:-20px;width:6px;height:6px;border-radius:50%;background:#8fbe9b;box-shadow:0 0 14px #8fbe9b80;animation:float-particle var(--particle-duration) ease-in-out infinite;animation-delay:var(--particle-delay)}
.particle-1{left:7%;--particle-duration:18s;--particle-delay:-4s}.particle-2{left:16%;width:4px;height:4px;--particle-duration:23s;--particle-delay:-15s}.particle-3{left:27%;--particle-duration:20s;--particle-delay:-8s}.particle-4{left:38%;width:8px;height:8px;--particle-duration:27s;--particle-delay:-20s}.particle-5{left:49%;--particle-duration:19s;--particle-delay:-12s}.particle-6{left:59%;width:4px;height:4px;--particle-duration:24s;--particle-delay:-2s}.particle-7{left:68%;--particle-duration:22s;--particle-delay:-17s}.particle-8{left:76%;width:8px;height:8px;--particle-duration:29s;--particle-delay:-10s}.particle-9{left:83%;--particle-duration:21s;--particle-delay:-6s}.particle-10{left:90%;width:4px;height:4px;--particle-duration:25s;--particle-delay:-19s}.particle-11{left:32%;width:5px;height:5px;--particle-duration:26s;--particle-delay:-14s}.particle-12{left:94%;width:7px;height:7px;--particle-duration:30s;--particle-delay:-23s}
.block-container{box-sizing:border-box;width:100%;max-width:1240px;min-width:0;padding:2.3rem 2.2rem 3rem}
h1,h2,h3{letter-spacing:-.045em!important}h1{font-weight:750!important}
[data-testid="stAppViewContainer"] .main .block-container,[data-testid="stMain"] .block-container{animation:soft-in .42s ease-out both}
[data-testid="stAppViewContainer"] .main,[data-testid="stMain"]{box-sizing:border-box;min-width:0;max-width:100%}
[data-testid="stAppViewContainer"] .main .block-container,[data-testid="stMain"] .block-container{position:relative;z-index:0}
[data-testid="stSidebar"] [data-testid="stVerticalBlock"]{animation:soft-in .38s ease-out both}
[data-testid="stSidebar"]{position:relative;z-index:2;background:#102F29;border-right:0}
[data-testid="stSidebar"] *{color:#e4eee5}
[data-testid="stSidebar"] [data-testid="stExpander"]{background:#1c3c34}
[data-testid="stSidebar"] summary{background:#1c3c34!important;color:#e4eee5!important}
[data-testid="stSidebar"] button{background:#264b3e;color:white;border-color:#406354}
[data-testid="stSidebar"] [data-testid="stBaseButton-primary"]{background:#bcd89b;color:#153e30;border-color:#bcd89b}
[data-testid="stSidebar"] [data-testid="stBaseButton-primary"] button,[data-testid="stSidebar"] [data-testid="stBaseButton-primary"] button *{color:#153e30!important}
[data-testid="stSidebar"] [data-testid="stSelectbox"] [data-baseweb="select"] > div{background:#f8fafc;border-color:#cbd5e1;color:#1e293b}
[data-testid="stSidebar"] [data-testid="stSelectbox"] [data-baseweb="select"] input,[data-testid="stSidebar"] [data-testid="stSelectbox"] [data-baseweb="select"] [role="combobox"]{color:#0f172a!important;-webkit-text-fill-color:#0f172a!important;opacity:1}
[data-testid="stSidebar"] [data-testid="stSelectbox"] [data-baseweb="select"] [data-testid="stMarkdownContainer"],[data-testid="stSidebar"] [data-testid="stSelectbox"] [data-baseweb="select"] div,[data-testid="stSidebar"] [data-testid="stSelectbox"] [data-baseweb="select"] div *{color:#0f172a!important;-webkit-text-fill-color:#0f172a!important}
[data-baseweb="popover"] [role="option"]{color:#1e293b!important}
[data-testid="stSidebar"] [data-testid="stVerticalBlock"]:has(.st-key-sidebar-footer){min-height:calc(100vh - 2.5rem)}
[data-testid="stSidebar"] .st-key-sidebar-footer{margin-top:auto;padding-top:.25rem;border-top:1px solid #ffffff20}
[data-testid="stSidebar"] .st-key-sidebar-footer [data-testid="stCaptionContainer"]{color:#aac0b1;font-size:11px}
[data-testid="stSidebar"] [data-testid="stRadio"] label{font-weight:550}
[data-testid="stMetric"]{border:1px solid #e0e7dc;background:white;border-radius:18px;padding:22px;box-shadow:0 5px 18px #16372904;animation:rise .45s ease both;transition:transform .24s ease,box-shadow .24s ease,border-color .24s ease}
[data-testid="stMetric"]:hover{transform:translateY(-3px);box-shadow:0 12px 26px #16372912;border-color:#c9dac4}
[data-testid="stMetricLabel"]{color:#667a70;font-size:13px}
[data-testid="stMetricValue"]{letter-spacing:-.055em;font-weight:650}
[data-testid="stForm"]{background:white;border:1px solid #dfe8dc;border-radius:20px;padding:24px;transition:box-shadow .25s ease,border-color .25s ease}
[data-testid="stForm"]:focus-within{border-color:#9fbea5;box-shadow:0 10px 28px #1637290d}
.stButton button,.stDownloadButton button,.stFormSubmitButton button{border-radius:11px;min-height:43px;transition:transform .18s,box-shadow .18s}
.stButton button:hover,.stDownloadButton button:hover,.stFormSubmitButton button:hover{transform:translateY(-2px);box-shadow:0 6px 15px #143c2814}
[data-testid="stExpander"]{border-radius:16px;transition:border-color .22s ease,box-shadow .22s ease}
[data-testid="stExpander"]:has(summary:hover){border-color:#b8cfba;box-shadow:0 7px 18px #1637290b}
[data-testid="stExpander"] details[open] summary{border-bottom-color:#dce7d9}
[data-testid="stExpander"] details[open] > div{animation:soft-in .28s ease-out both}
[data-testid="stTabs"] button[role="tab"]{transition:color .2s ease,background-color .2s ease,transform .2s ease}
[data-testid="stTabs"] button[role="tab"]:hover{transform:translateY(-1px)}
[data-testid="stTabs"] [data-baseweb="tab-highlight"]{transition:transform .25s ease,width .25s ease}
[data-testid="stSegmentedControl"]{background:#eef3ec;border:1px solid #dce5da;border-radius:12px;padding:4px}
[data-testid="stSegmentedControl"] button{border-radius:9px!important;min-height:38px;color:#40564a}
[data-testid="stSegmentedControl"] button[aria-pressed="true"]{background:#245c47!important;color:#fff!important;box-shadow:0 2px 5px #16372920}
[data-testid="stTextArea"] textarea,[data-testid="stTextInput"] input{border-radius:12px;transition:border-color .2s ease,box-shadow .2s ease,background-color .2s ease}
[data-testid="stTextArea"] textarea:focus,[data-testid="stTextInput"] input:focus{border-color:#79a487;box-shadow:0 0 0 3px #79a4872b;background:#fcfefb}
.hero{background:linear-gradient(115deg,#173e31,#245c47);border-radius:24px;padding:32px 36px;margin:10px 0 27px;color:#f1f6ec;position:relative;overflow:hidden;animation:rise .5s ease}
.hero:after{content:'↗';position:absolute;right:30px;top:-45px;font-size:220px;color:#b5d59a14;pointer-events:none}
.hero h2{color:#f1f6ec!important;font-size:34px;margin:8px 0!important;max-width:80%}
.hero p{color:#c3d8c4;max-width:620px;font-size:15px;line-height:1.7;margin:0}
.eyebrow{font-size:11px;font-weight:700;letter-spacing:.17em;text-transform:uppercase;color:#bad89e}
.brand{display:flex;align-items:center;gap:12px;font-size:26px;font-weight:700;letter-spacing:-1px;padding:5px 0 30px}
.brand-icon{display:inline-grid;place-items:center;width:42px;height:42px;background:#bcd89b;color:#153e30!important;border-radius:13px;animation:pulse 4s infinite}
.st-key-saysale-brand{padding:.45rem .15rem 1rem}
.st-key-saysale-brand [data-testid="stImage"]{background:transparent;margin:0;padding:0}
.st-key-saysale-brand [data-testid="stImage"] img{display:block;width:42px!important;height:auto!important;max-width:100%!important;object-fit:contain;animation:logo-bounce 2.4s ease-in-out infinite}
.sidebar-brand-name{color:#f3f7f3;font-size:22px;font-weight:750;letter-spacing:-.04em;line-height:1}
.small-label{font-size:11px;letter-spacing:.16em;text-transform:uppercase;color:#829c8e!important;margin-bottom:12px}
.steps{display:flex;gap:8px;margin:8px 0 20px;flex-wrap:wrap}.step{font-size:12px;color:#60756b;background:#e9efe5;padding:8px 13px;border-radius:30px}.step.active{color:#f6fbf1;background:#245c47}
.stock-card{background:white;border:1px solid #e0e7dc;border-radius:16px;padding:18px;margin-bottom:12px;animation:rise .4s ease;transition:transform .22s ease,box-shadow .22s ease,border-color .22s ease}.stock-card:hover{transform:translateY(-3px);box-shadow:0 9px 20px #16372912;border-color:#c9dac4}.stock-name{font-size:14px;font-weight:650}.stock-number{font-size:28px;font-weight:700;letter-spacing:-1px}.muted{font-size:12px;color:#75877b}.tag{float:right;display:inline-flex;align-items:center;gap:6px;font-size:10px;font-weight:700;padding:5px 9px;border-radius:20px;background:#edf3e7;color:#416337;transition:transform .2s ease}.tag:hover{transform:scale(1.04)}.tag.low{background:#fff0d8;color:#9a6115}.status-dot{width:7px;height:7px;border-radius:50%;background:#54845a}.tag.low .status-dot{background:#c17b22}.empty{padding:32px;border:1px dashed #bdcdbb;border-radius:16px;text-align:center;color:#738274;background:#f1f5ed}
.pending-card-title{display:flex;align-items:center;gap:9px;color:#254d3a;font-size:17px;font-weight:700;margin-bottom:6px}.pending-card-icon{display:inline-grid;place-items:center;width:28px;height:28px;border-radius:50%;background:#edf3e7;color:#416337}.pending-card-copy{color:#52645a;margin:0 0 10px}.pending-source{font-size:12px;color:#75877b;overflow-wrap:anywhere}
.activity-table-wrap{overflow-x:auto;border:1px solid #e0e7dc;border-radius:14px;background:white}.activity-table{width:100%;min-width:720px;border-collapse:separate;border-spacing:0;text-align:left;font-size:13px}.activity-table th{padding:13px 15px;background:#f2f5ef;color:#52645a;font-size:11px;font-weight:700;letter-spacing:.04em;white-space:nowrap}.activity-table td{padding:13px 15px;border-top:1px solid #edf0eb;color:#31443a;vertical-align:middle}.activity-table tbody tr:nth-child(even){background:#f8faf7}.activity-table tbody tr{transition:background-color .2s ease,transform .2s ease}.activity-table tbody tr:hover td{background:#eef4ec}.activity-table tbody tr:hover{transform:translateX(2px)}.type-badge{display:inline-flex;align-items:center;border-radius:20px;padding:4px 9px;font-size:11px;font-weight:700;white-space:nowrap;transition:transform .2s ease}.type-badge:hover{transform:scale(1.05)}.type-badge.sale{background:#e8f3e9;color:#28613a}.type-badge.void{background:#fce9e7;color:#9c3932}.type-badge.expense{background:#fff1dc;color:#8b5d17}.type-badge.restock{background:#e9eff8;color:#3d5f8a}
.st-key-parse_ai_button button,[class*="st-key-parse_ai_button"] button{background:#245c47!important;color:#fff!important;border:1px solid #245c47!important}.st-key-parse_ai_button button:hover,[class*="st-key-parse_ai_button"] button:hover{background:#1c4938!important}.st-key-manual_draft_button button,[class*="st-key-manual_draft_button"] button{background:transparent!important;color:#245c47!important;border:1px solid #7d9b87!important}.st-key-manual_draft_button button:hover,[class*="st-key-manual_draft_button"] button:hover{background:#edf3e7!important;border-color:#245c47!important}
[class*="st-key-appr_"] button,[class*="st-key-appr_"] button *{background:#e8f3e9!important;color:#1f5b34!important;border:1px solid #9fc9a5!important}[class*="st-key-appr_"] button:hover,[class*="st-key-appr_"] button:hover *{background:#dceede!important;color:#174728!important}
[class*="st-key-rev_"] button,[class*="st-key-rev_"] button *{background:#f8fafc!important;color:#263b32!important;border:1px solid #9aaea2!important}[class*="st-key-rev_"] button:hover,[class*="st-key-rev_"] button:hover *{background:#edf2ef!important;color:#1a2d24!important}
[class*="st-key-rej_"] button,[class*="st-key-rej_"] button *{background:#fff1ef!important;color:#8f2f29!important;border:1px solid #e5aaa4!important}[class*="st-key-rej_"] button:hover,[class*="st-key-rej_"] button:hover *{background:#ffe3df!important;color:#75231e!important}
[class*="st-key-pending-card-"]{border-color:#dce7d9!important;border-radius:14px!important;background:#fff}
.pending-review-reason{background:#fffbeb;border:1px solid #fde68a;border-radius:10px;padding:10px 14px;color:#78350f;font-size:13px;line-height:1.45;margin:8px 0}
.activity-table caption{padding:10px;text-align:left;color:#75877b}
.activity-table th:first-child{border-radius:13px 0 0 0}.activity-table th:last-child{border-radius:0 13px 0 0}
.footer{font-size:11px;color:#809085;border-top:1px solid #e0e7dc;margin-top:35px;padding-top:18px}
@media(prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
@media(max-width:900px){
  .block-container{max-width:none;padding-left:1.5rem;padding-right:1.5rem}
  [data-testid="stAppViewContainer"] .main,[data-testid="stMain"]{min-width:0}
}
@media(max-width:640px){.block-container{padding:3.5rem 1rem 1rem}.hero{padding:23px}.hero h2{font-size:26px;max-width:100%}.hero:after{display:none}[data-testid="stMetric"]{padding:15px}}
</style>'''


DARK_STYLE = '''<style>
[data-testid="stAppViewContainer"],[data-testid="stHeader"]{background:#0d1714!important}
[data-testid="stAppViewContainer"] .main,[data-testid="stMain"]{color:#e5eee8}
[data-testid="stAppViewContainer"] .main .block-container,[data-testid="stMain"] .block-container{color:#e5eee8}
[data-testid="stMain"] h1,[data-testid="stMain"] h2,[data-testid="stMain"] h3,[data-testid="stMain"] h4,[data-testid="stMain"] h5,[data-testid="stMain"] h6,[data-testid="stHeading"],[data-testid="stHeading"] *,[data-testid="stMarkdownContainer"] h1,[data-testid="stMarkdownContainer"] h2,[data-testid="stMarkdownContainer"] h3,[data-testid="stMarkdownContainer"] h4,[data-testid="stAppViewContainer"] .main h1,[data-testid="stAppViewContainer"] .main h2,[data-testid="stAppViewContainer"] .main h3,[data-testid="stAppViewContainer"] .main h4{color:#f0f7f1!important}
.hero h2{color:#f1f6ec!important}
[data-testid="stMarkdownContainer"] p,[data-testid="stMarkdownContainer"] li,
[data-testid="stText"],[data-testid="stCaptionContainer"]{color:#c7d5cc}
[data-testid="stMetric"],[data-testid="stForm"],.activity-table-wrap,.stock-card{background:#17241f;border-color:#2c4439;color:#e5eee8}
[data-testid="stMetricLabel"],.muted,.activity-table caption{color:#9db2a4}
[data-testid="stMetricValue"],.stock-number,.stock-name{color:#f0f7f1}
[data-testid="stExpander"]{background:#17241f;border-color:#2c4439}
[data-testid="stExpander"] summary{color:#e5eee8}
[data-testid="stExpander"] details[open] summary{border-bottom-color:#2c4439}
[data-testid="stTextArea"] textarea,[data-testid="stTextInput"] input,
[data-baseweb="select"]>div{background:#101b17!important;border-color:#385447!important;color:#e5eee8!important}
[data-testid="stTextArea"] textarea::placeholder,[data-testid="stTextInput"] input::placeholder{color:#80978a}
[data-testid="stSelectbox"] [role="combobox"],[data-testid="stSelectbox"] [data-testid="stMarkdownContainer"],[data-testid="stSelectbox"] [data-baseweb="select"] div *{color:#e5eee8!important;-webkit-text-fill-color:#e5eee8!important}
[data-testid="stSidebar"] [data-baseweb="select"]>div{background:#f8fafc!important;border-color:#cbd5e1!important}
[class*="st-key-pending-card-"]{background:#17241f!important;border-color:#2c4439!important;color:#e5eee8!important}
[class*="st-key-pending-card-"] [data-testid="stMarkdownContainer"],
[class*="st-key-pending-card-"] [data-testid="stText"],
[class*="st-key-pending-card-"] [data-testid="stCaptionContainer"]{color:#a9bcae!important}
[class*="st-key-pending-card-"] .pending-card-title{color:#dcebe0!important}
[class*="st-key-pending-card-"] .pending-card-copy,
[class*="st-key-pending-card-"] .pending-card-copy strong{color:#e5eee8!important}
[class*="st-key-pending-card-"] .pending-source{color:#a9bcae!important}
[class*="st-key-pending-card-"] .pending-card-icon{background:#294337;color:#dcebe0}
[class*="st-key-appr_"] button{background:#e8f3e9!important;color:#1f5b34!important;border-color:#9fc9a5!important}
[class*="st-key-appr_"] button *{color:#1f5b34!important}
[class*="st-key-rev_"] button{background:#f8fafc!important;color:#263b32!important;border-color:#9aaea2!important}
[class*="st-key-rev_"] button *{color:#263b32!important}
[class*="st-key-rej_"] button{background:#fff1ef!important;color:#8f2f29!important;border-color:#e5aaa4!important}
[class*="st-key-rej_"] button *{color:#8f2f29!important}
[class*="st-key-appr_"] button:focus-visible,[class*="st-key-rev_"] button:focus-visible,[class*="st-key-rej_"] button:focus-visible{outline:3px solid #9ac6a7!important;outline-offset:2px}
[data-testid="stRadio"] label,[data-testid="stCheckbox"] label{color:#d4e1d8}
.steps .step{background:#20352c;color:#b7cbbd}
.activity-table th{background:#20352c;color:#b7cbbd}
.activity-table td{border-top-color:#2c4439;color:#d7e4db}
.activity-table tbody tr:nth-child(even){background:#192a23}
.activity-table tbody tr:hover td{background:#244035}
.empty{background:#17241f;border-color:#456252;color:#a9bcae}
.pending-card-title{color:#dcebe0}.pending-card-copy,.pending-source{color:#a9bcae}
.pending-review-reason{background:#fffbeb;color:#78350f;border-color:#fde68a}
[data-testid="stSidebar"]{background:#08100d}
.particle-field{opacity:.42}
</style>'''


def _minify_css(css):
    """Put a <style> block on one line.

    Streamlit renders st.markdown() through a markdown parser. A multi-line
    <style> block that shares a string with another one (e.g. STYLE + DARK_STYLE)
    stops being treated as raw HTML partway through, and the rest of the CSS
    shows up as visible page text. One line can't be split that way.
    """
    return ''.join(line.strip() for line in css.splitlines())


STYLE = _minify_css(STYLE)
DARK_STYLE = _minify_css(DARK_STYLE)


def particle_background():
    particles = ''.join(
        f'<span class="particle particle-{index}" aria-hidden="true"></span>'
        for index in range(1, 13)
    )
    st.markdown(f'<div class="particle-field" aria-hidden="true">{particles}</div>',
                unsafe_allow_html=True)


def hero(label, title, description):
    st.markdown(f'<div class="hero"><div class="eyebrow">{_cell(label)}</div><h2>{_cell(title)}</h2><p>{_cell(description)}</p></div>', unsafe_allow_html=True)


def shop_summary(sales_total, expense_total, sales_count, units_on_shelves, language='en'):
    from i18n import tr
    t=lambda text:tr(text,language)
    with st.expander(t('Shop summary'),expanded=False):
        columns=st.columns(4)
        columns[0].metric(t('Sales recorded'),sales_total)
        columns[1].metric(t('Expenses recorded'),expense_total)
        columns[2].metric(t('Sales transactions'),sales_count)
        columns[3].metric(t('Units on shelves'),units_on_shelves)
        st.caption(t('All-time totals · Restocks tracked separately · These figures are not profit.'))


def stock_cards(items, language='en'):
    from i18n import tr
    t=lambda text:tr(text,language)
    if not items:
        st.info(t('Your inventory is empty. Add a product or load demo stock in Settings.'))
        return
    cols=st.columns(min(3,len(items)))
    for i,p in enumerate(items):
        q,threshold=p['quantity'],p['threshold']
        low=q<threshold or q==0
        status=t('Out of stock' if q==0 else 'Low stock' if low else 'In stock')
        with cols[i%len(cols)]:
            st.markdown(f'<div class="stock-card"><span class="tag {"low" if low else ""}"><span class="status-dot" aria-hidden="true"></span>{_cell(status)}</span><div class="stock-name">{_cell(p["name"])}</div><div class="stock-number">{q:,} <span class="muted">{_cell(t("units"))}</span></div><div class="muted">{_cell(t("Alert below"))} {threshold:,}</div></div>',unsafe_allow_html=True)


def pending_reason_copy(reasons, clarification_question=None, language='en'):
    from i18n import tr
    t=lambda text:tr(text,language)
    if clarification_question:
        return str(clarification_question)
    reasons=' '.join(str(reason) for reason in (reasons or []))
    if 'not in inventory' in reasons:
        return t('Match this item to a product in your inventory.')
    if 'Oversell risk' in reasons or 'Insufficient stock' in reasons:
        return t('Check the requested quantity against available stock.')
    if 'currency' in reasons.lower():
        return t('Confirm this transaction uses the shop currency.')
    if 'Missing required fields' in reasons or 'clarification' in reasons.lower():
        return t('Some transaction details need clarification.')
    if 'Confidence' in reasons:
        return t('Review the transaction details before approving.')
    return t('Review this draft before approving.')


def activity_table(rows, timezone='UTC', language='en'):
    from i18n import tr
    t=lambda text:tr(text,language)
    rows=[dict(row) for row in rows]
    frame=ledger_frame(rows,timezone,language)
    columns=[t('Time'),t('Type'),t('Product'),t('Quantity'),t('Unit price'),t('Amount'),t('Currency'),t('Note')]
    headers=''.join(f'<th scope="col">{_cell(column)}</th>' for column in columns)
    body=[]
    for index,record in enumerate(frame.to_dict('records')):
        original=rows[index]
        kind=original.get('type','')
        safe_kind=kind if kind in ('sale','void','expense','restock') else 'other'
        cells=[]
        for column in columns:
            value=record.get(column)
            if column==t('Type'):
                cell=f'<span class="type-badge {safe_kind}">{_cell(value or "")}</span>'
            elif value is None or pd.isna(value):
                cell='—'
            else:
                cell=_cell(value)
            cells.append(f'<td>{cell}</td>')
        body.append('<tr>'+''.join(cells)+'</tr>')
    table=f'<div class="activity-table-wrap"><table class="activity-table" aria-label="{_cell(t("Latest activity"))}"><thead><tr>{headers}</tr></thead><tbody>{"".join(body)}</tbody></table></div>'
    st.markdown(table,unsafe_allow_html=True)


def ledger_frame(rows,timezone='UTC',language='en',display=True):
    from i18n import tr
    from intl import local_time, major_units
    from babel.numbers import format_decimal
    t=lambda text:tr(text,language) if display else text
    data=[]
    for r in rows:
        currency=r['currency']
        def amount(value):
            if value is None: return None
            value=major_units(value,currency)
            return format_decimal(value,locale=language,decimal_quantization=False) if display else str(value)
        data.append({t('Time'):local_time(r['created_at'],timezone) if display else r['created_at'],t('Type'):t(r['type']) if display else r['type'],t('Product'):r['item_name'] or t('General expense'),t('Quantity'):r['quantity'],t('Unit price'):amount(r['unit_price_minor']),t('Amount'):amount(r['amount_minor']),t('Currency'):currency,t('Note'):r['note'],t('Source'):r['source_text'],t('Record ID'):r['id'],'Created by':r['created_by']})
    frame=pd.DataFrame(data)
    quantity_column=t('Quantity')
    if quantity_column in frame:
        # Rows without a quantity (expenses) turn the column into floats, which
        # would show "5.0" instead of "5". Use a nullable integer column.
        try:
            frame[quantity_column]=pd.to_numeric(frame[quantity_column]).astype('Int64')
        except (TypeError,ValueError):
            pass
    return frame


_NUMERIC_TEXT=re.compile(r'[+-]?\d[\d\s.,]*')


def _csv_safe(value):
    """Neutralise spreadsheet formula injection without mangling plain numbers."""
    if not isinstance(value,str):
        return value
    if value.startswith(('\t','\r')):
        return "'"+value
    stripped=value.lstrip()
    if stripped.startswith(('=','+','-','@')) and not _NUMERIC_TEXT.fullmatch(stripped.rstrip()):
        return "'"+value
    return value


def csv_bytes(frame):
    exported=frame.copy()
    for col in exported.columns:
        # Check both dtypes: pandas 3 stores text as "str", not "object".
        if pd.api.types.is_object_dtype(exported[col]) or pd.api.types.is_string_dtype(exported[col]):
            exported[col]=exported[col].map(_csv_safe)
    return exported.to_csv(index=False).encode('utf-8-sig')
