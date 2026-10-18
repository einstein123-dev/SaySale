import os
import time
import uuid
import sqlite3
import logging
from html import escape
from decimal import Decimal
from pathlib import Path
import streamlit as st
from streamlit_cookies_controller import CookieController
from babel.numbers import parse_decimal, format_decimal, NumberFormatError
from babel import Locale
import store
from intl import LANGUAGES, CURRENCIES, COUNTRIES, TIMEZONES, money_label, minor_units, major_units, local_time
from i18n import tr
import ai_parser
from ai_parser import parse_transaction, parse_multi_transaction, parse_media_transaction
import ai_cfo
import ai_automation
import email_service
from ui import (DARK_STYLE, STYLE, activity_table, csv_bytes, hero, ledger_frame,
                particle_background, pending_reason_copy, sales_over_time_frame,
                shop_summary, stock_cards)

LOGO_PATH=Path(__file__).resolve().parent/'logo'/'saysale-icon.png'
st.set_page_config(page_title='SaySale · Shop management',page_icon=str(LOGO_PATH),layout='wide')
st.session_state.setdefault('dark_mode',False)
st.markdown(STYLE + (DARK_STYLE if st.session_state.dark_mode else ''),unsafe_allow_html=True)
particle_background()
store.init_db()
cookie_controller=CookieController(key='saysale_cookies')
AUTH_COOKIE='saysale_auth'


def clear_draft():
    for k in ('draft','draft_id','draft_source','draft_shop','draft_generation','latency','invite_code','current_briefing','cfo_answer'):
        st.session_state.pop(k,None)


def reset_login():
    # Remove shop data, drafts and password widget state at logout/session expiry.
    lang=st.session_state.get('language','en')
    dark_mode=st.session_state.get('dark_mode',False)
    if cookie_controller.get(AUTH_COOKIE) is not None:
        cookie_controller.remove(AUTH_COOKIE)
    st.session_state.clear()
    st.session_state.language=lang
    st.session_state.dark_mode=dark_mode


# Streamlit session state is cleared by a full browser refresh. Restore the
# server-validated session token from its short-lived browser cookie.
if 'auth_token' not in st.session_state:
    saved_token=cookie_controller.get(AUTH_COOKIE)
    if isinstance(saved_token,str) and saved_token:
        st.session_state.auth_token=saved_token


with st.sidebar:
    with st.container(key='saysale-brand'):
        logo_col,brand_col=st.columns([1,4],vertical_alignment='center',gap='small')
        with logo_col:
            st.image(str(LOGO_PATH),width=42)
        with brand_col:
            st.markdown('<div class="sidebar-brand-name">SaySale</div>',unsafe_allow_html=True)
    if 'auth_token' not in st.session_state:
        st.checkbox('Dark mode',key='dark_mode',help='Switch between dark and light appearance.')
        language=st.selectbox('Language / Langue / Idioma',list(LANGUAGES),format_func=lambda k:LANGUAGES[k],key='language')
    else:
        language=st.session_state.get('language','en')

if st.session_state.get('previous_language')!=language:
    clear_draft()
    st.session_state.previous_language=language

t=lambda text:tr(text,language)

def flash(message):
    st.session_state.flash=message
    st.rerun()


def show_flash():
    if 'flash' in st.session_state:
        st.success(t(st.session_state.pop('flash')))


def setting(key):
    value=os.getenv(key)
    if not value:
        try: value=st.secrets.get(key,'')
        except (FileNotFoundError,st.errors.StreamlitSecretNotFoundError): value=''
    return value.strip() if isinstance(value,str) else ''


def error(e):
    if isinstance(e,PermissionError):
        st.error(str(e))
    elif isinstance(e,sqlite3.Error):
        logging.getLogger(__name__).warning('Storage error: %s',type(e).__name__)
        st.error('Storage unavailable. Please retry. No partial transaction was saved.')
    else:
        st.error(t(str(e)))


def number(value):
    if not isinstance(value,str) or not value.strip():
        raise ValueError('Enter a monetary amount.')
    try:
        return parse_decimal(value.strip(),locale=language,strict=True)
    except NumberFormatError:
        raise ValueError(t('Enter amounts using your selected language’s number format.'))


def input_number(value):
    return format_decimal(Decimal(str(value)),locale=language,decimal_quantization=False,group_separator=False) if value is not None else ''


if 'auth_token' not in st.session_state:
    hero(t('Every shop. A clearer picture.'),t('Your words. Your currency. Your records.'),t('Describe a transaction, review the details, and keep sales and stock in step.'))
    show_flash()
    login_tab,register_tab=st.tabs([t('Sign in'),t('Create account')])
    with login_tab:
        with st.form('login'):
            email=st.text_input(t('Email'),max_chars=254)
            password=st.text_input(t('Password'),type='password',max_chars=128)
            if st.form_submit_button(t('Sign in'),type='primary'):
                try:
                    token=store.login(email,password)
                    reset_login()
                    st.session_state.auth_token=token
                    cookie_controller.set(
                        AUTH_COOKIE,
                        token,
                        max_age=store.SESSION_SECONDS,
                        secure=(st.context.url or '').startswith('https://'),
                        same_site='strict'
                    )
                    st.rerun()
                except (ValueError,sqlite3.Error) as e: error(e)
        st.caption(t('Your session lasts up to 8 hours. Refreshing should keep you signed in in this browser.'))
    with register_tab:
        with st.form('register'):
            name=st.text_input(t('Name'),max_chars=80)
            email=st.text_input(t('Email'),key='signup_email',max_chars=254)
            password=st.text_input(t('Password'),type='password',key='signup_password',max_chars=128)
            repeated=st.text_input(t('Repeat password'),type='password',max_chars=128)
            st.caption(t('Use 12–128 characters. Email verification and email recovery are not configured.'))
            if st.form_submit_button(t('Create account'),type='primary'):
                try:
                    if password!=repeated: raise ValueError(t('Passwords do not match.'))
                    store.register(email,name,password)
                    reset_login()
                    flash('Account created. You can sign in now.')
                except (ValueError,sqlite3.Error) as e: error(e)
    st.caption(t('Use synthetic data only. Never include customer details.'))
    st.caption(t('Read the developer guide before public deployment.'))
    st.stop()

TOKEN=st.session_state.auth_token
try:
    user=store.current_user(TOKEN)
    shops=store.list_shops(TOKEN)
except PermissionError:
    reset_login()
    st.rerun()
except sqlite3.Error as e:
    error(e)
    st.stop()

if shops:
    if 'next_shop' in st.session_state:
        st.session_state.shop_choice=st.session_state.pop('next_shop')
    ids=[s['id'] for s in shops]
    if st.session_state.get('shop_choice') not in ids:
        st.session_state.shop_choice=ids[0]
    shop_id=st.session_state.shop_choice
    selected_shop=next(s for s in shops if s['id']==shop_id)
    if st.session_state.get('previous_shop')!=shop_id:
        clear_draft()
        st.session_state.previous_shop=shop_id
else:
    shop_id=None
    selected_shop=None

if shop_id:
    try:
        state=store.snapshot(TOKEN,shop_id)
    except PermissionError as e:
        clear_draft()
        error(e)
        st.stop()
    except sqlite3.Error as e:
        error(e)
        st.stop()
    shop=state['shop']
    items=state['products']
    rows=state['transactions']
    role=state['role']
    allowed=store.PERMISSIONS[role]
    currency=shop['currency']
    fmt=lambda value:money_label(value,currency,language)
else:
    shop=None
    allowed=set()
    state={}

def choose_navigation(page):
    st.session_state.active_page=page


page_groups={
    'core':('Core Operations',['Record & overview','Inventory','Ledger']),
    'intelligence':('Intelligence',['AI Advisor & CFO']),
    'administration':('Administration',['Team','Settings','Account']),
}
if 'active_page' not in st.session_state:
    st.session_state.active_page='Record & overview' if shops else 'Account'
if not shops:
    st.session_state.active_page='Account'

with st.sidebar:
    if shops:
        st.selectbox(t('Your shops'),ids,format_func=lambda id:next(s['name'] for s in shops if s['id']==id),key='shop_choice')
        pending_count=len(state.get('pending',[]))
        for key,(label,pages) in page_groups.items():
            st.caption(t(label))
            for item in pages:
                label_text=f"{t(item)}  ·  {pending_count}" if item=='Record & overview' and pending_count else t(item)
                st.button(label_text,key=f'sidebar_nav_{key}_{item}',type='primary' if st.session_state.active_page==item else 'secondary',width='stretch',on_click=choose_navigation,args=(item,))
        page=st.session_state.active_page
    else:
        st.caption(t('Administration'))
        st.button(t('Account'),key='sidebar_nav_account',type='primary',width='stretch',on_click=choose_navigation,args=('Account',))
        page='Account'
    with st.container(key='sidebar-footer'):
        st.divider()
        st.checkbox('Dark mode',key='dark_mode',help='Switch between dark and light appearance.')
        language=st.selectbox('Language / Langue / Idioma',list(LANGUAGES),format_func=lambda k:LANGUAGES[k],key='language')
        if st.session_state.get('previous_language')!=language:
            clear_draft()
            st.session_state.previous_language=language
        st.markdown(f"**{user['name']}**")
        if selected_shop:
            st.caption(f"{t('Role')}: {t(role)} · {selected_shop['currency']} · {selected_shop['timezone']}")
        ready=bool(setting('GEMINI_API_KEY') and setting('GEMINI_MODEL'))
        st.caption(t('AI configured · connection unverified' if ready else 'Manual mode'))
        if st.button(t('Sign out'),width='stretch'):
            try: store.logout(TOKEN)
            finally:
                reset_login()
            st.rerun()
    ready=bool(setting('GEMINI_API_KEY') and setting('GEMINI_MODEL'))
    st.caption(t('AI configured · connection unverified' if ready else 'Manual mode'))

show_flash()


def shop_creation():
    with st.expander(t('Create shop'),expanded=not shops):
        with st.form('create_shop'):
            name=st.text_input(t('Shop name'),max_chars=100)
            locale_countries=Locale(language).territories
            country=st.selectbox(t('Country / region'),sorted(COUNTRIES),format_func=lambda c:locale_countries.get(c,c),index=sorted(COUNTRIES).index('US'))
            currency=st.selectbox(t('Currency'),CURRENCIES,index=CURRENCIES.index('USD'))
            timezone=st.selectbox(t('Timezone'),TIMEZONES,index=TIMEZONES.index('UTC'))
            st.caption(t('Currency is fixed for this shop to protect existing records. Create a separate shop for another currency.'))
            if st.form_submit_button(t('Create shop'),type='primary'):
                try:
                    created=store.create_shop(TOKEN,name,country,currency,timezone)
                    st.session_state.next_shop=created
                    st.session_state.active_page='Record & overview'
                    clear_draft()
                    flash('Shop created.')
                except (ValueError,PermissionError,sqlite3.Error) as e: error(e)
    with st.expander(t('Join shop'),expanded=not shops):
        with st.form('join'):
            code=st.text_input(t('Invitation code'),type='password',max_chars=200)
            if st.form_submit_button(t('Join shop')):
                try:
                    joined=store.accept_invite(TOKEN,code)
                    st.session_state.next_shop=joined
                    st.session_state.active_page='Record & overview'
                    clear_draft()
                    flash('Invitation accepted.')
                except (ValueError,PermissionError,sqlite3.Error) as e: error(e)


if page=='Account':
    if language == 'es':
        st.radio(t('Page navigation'),[t('Account')],label_visibility='collapsed')
    hero(t('Account'),user['name'],user['email'])
    if not shops: st.info(t('Create your first shop or join one with an invitation.'))
    shop_creation()
    with st.expander(t('Change password')):
        with st.form('password_change'):
            current=st.text_input(t('Current password'),type='password',max_chars=128)
            new=st.text_input(t('New password'),type='password',max_chars=128)
            repeat=st.text_input(t('Repeat password'),type='password',max_chars=128)
            if st.form_submit_button(t('Change password')):
                try:
                    if new!=repeat: raise ValueError(t('Passwords do not match.'))
                    store.change_password(TOKEN,current,new)
                    reset_login()
                    flash('Password changed. Sign in again.')
                except (ValueError,PermissionError,sqlite3.Error) as e: error(e)

if shop and page=='Record & overview':
    hero(shop['name'],t('Your words. Your currency. Your records.'),t('Describe a transaction, review the details, and keep sales and stock in step.'))
    low=[p for p in items if p['quantity']<p['threshold'] or p['quantity']==0]
    if low: st.warning(t('Low stock')+' · '+', '.join(f"{p['name']}: {p['quantity']}" for p in low))
    def new_draft(draft=None, src=''):
        clear_draft()
        st.session_state.draft=draft or {}
        st.session_state.draft_id=str(uuid.uuid4())
        st.session_state.draft_source=src or st.session_state.get('source_input','')
        st.session_state.draft_shop=shop_id
        st.session_state.draft_generation=shop['generation']

    pending_items=state.get('pending',[])
    if pending_items and any(k in allowed for k in ('sale','expense','restock')):
        with st.expander(f"📥 {t('Pending Inbound Inbox')} ({len(pending_items)})",expanded=True):
            for p_item in pending_items:
                pd=p_item.get('draft') or {}
                p_type=pd.get('type')
                type_label=str(t(p_type) or p_type or 'REVIEW REQUIRED').upper() if p_type else str(t('Review required') or 'REVIEW REQUIRED').upper()
                p_name=pd.get('item_name') or (t('General expense') if p_type=='expense' else t('Unspecified item'))
                p_qty=pd.get('quantity')
                p_price=pd.get('unit_price')
                p_exp=pd.get('amount_for_expense')
                p_amt=fmt(minor_units(p_price,currency)*(p_qty or 1) if p_price is not None else minor_units(p_exp,currency) if p_exp is not None else 0)
                reason=pending_reason_copy(pd.get('review_reasons'),pd.get('clarification_question'),language)
                with st.container(border=True,key=f"pending-card-{p_item['id']}"):
                    c_info,c_action=st.columns([3,2])
                    with c_info:
                        st.markdown(
                            f'<div class="pending-card-title"><span class="pending-card-icon" aria-hidden="true">!</span>{escape(t("Needs a quick check"))}</div>'
                            f'<div class="pending-card-copy"><strong>{escape(type_label)}</strong> · {escape(str(p_name))} · {escape(str(p_amt))}</div>'
                            f'<div class="pending-review-reason">{escape(reason)}</div>',
                            unsafe_allow_html=True,
                        )
                        source_text=p_item.get('source_text') or ''
                        if source_text: st.text(f"{t('Source')}: {source_text}")
                    with c_action:
                        c_appr,c_rev,c_rej=st.columns(3)
                        can_auto=bool(p_type in allowed and p_type in ('sale','expense','restock') and (p_type=='expense' or pd.get('item_name')))
                        if c_appr.button(t('Approve'),key=f"appr_{p_item['id']}",icon=':material/check_circle:',type='secondary',width='stretch',disabled=not can_auto):
                            try:
                                store.resolve_pending_draft(TOKEN,shop_id,p_item['id'],'approve')
                                flash('Saved. Your ledger and stock are up to date.')
                            except Exception as e: error(e)
                        if c_rev.button(t('Review'),key=f"rev_{p_item['id']}",icon=':material/edit_note:',type='secondary',width='stretch'):
                            new_draft(pd,p_item.get('source_text',''))
                            st.rerun()
                        if c_rej.button(t('Reject'),key=f"rej_{p_item['id']}",icon=':material/close:',type='secondary',width='stretch'):
                            try:
                                store.resolve_pending_draft(TOKEN,shop_id,p_item['id'],'reject')
                                flash('Draft rejected.')
                            except Exception as e: error(e)
                st.divider()
    kinds=[k for k in ('sale','expense','restock') if k in allowed]
    if kinds:
        st.subheader(t('What happened in your shop?'))
        input_mode=st.radio(t('Input method'),['Text','Voice','Receipt'],index=0,
                            horizontal=True,key='transaction_input_mode')
        st.markdown('<div class="steps">'+''.join(f'<span class="step">{t(s)}</span>' for s in ['01 · Describe','02 · Review','03 · Save'])+'</div>',unsafe_allow_html=True)
        consent=st.checkbox(t('Allow AI processing for transaction entry'))
        source=''
        uploaded_media=None
        recorded_voice=None
        if input_mode=='Text':
            source=st.text_area(t('What happened?'),max_chars=2000,height=100,key='source_input',placeholder=f'Sold 6 cooking oils at 25 {currency} each')
            x,y=st.columns([1.5,1])
        if input_mode=='Text' and x.button(t('Parse with AI'),type='primary',key='parse_ai_button',disabled=not (ready and consent and source.strip()),width='stretch'):
            clear_draft()
            try:
                store.authorize_ai(TOKEN,shop_id)
                start=time.perf_counter()
                with st.spinner(t('Preparing your draft…')):
                    result=parse_transaction(source,setting('GEMINI_API_KEY'),setting('GEMINI_MODEL'),currency=currency)
                new_draft(result)
                st.session_state.latency=time.perf_counter()-start
            except Exception as e:
                logging.getLogger(__name__).warning('Extraction failed: %s (%s)', type(e).__name__, e)
                st.error(t('AI is unavailable. Nothing was saved. Retry or enter manually.'))
        if input_mode=='Text' and y.button(t('Create manual draft'),key='manual_draft_button',type='secondary',width='stretch'): new_draft()
        if not ready: st.caption(t('AI is not configured. Manual entry is available.'))
        if input_mode=='Voice':
            st.caption(t('Record a voice memo to extract transaction details.'))
            recorded_voice=st.audio_input(t('Voice memo'),key='ambient_voice')
        elif input_mode=='Receipt':
            st.caption(t('Upload a receipt image to extract transaction details.'))
            uploaded_media=st.file_uploader(t('Receipt or invoice image'),type=['jpg','jpeg','png','webp'],key='ambient_receipt')
        if input_mode in ('Voice','Receipt') and (uploaded_media or recorded_voice) and ready:
            media_bytes=uploaded_media.getvalue() if uploaded_media else recorded_voice.getvalue()
            mime=uploaded_media.type if uploaded_media else (recorded_voice.type or 'audio/wav')
            auto_col1,auto_col2=st.columns(2)
            if auto_col1.button(t('Auto-commit with AI'),type='primary',key='btn_ambient_autocommit',disabled=not consent):
                try:
                    res=ai_automation.process_inbound_record(
                        shop_id=shop_id,user_token=TOKEN,media_bytes=media_bytes,mime_type=mime,
                        source_channel='receipt_ocr' if uploaded_media else 'voice_memo',
                        api_key=setting('GEMINI_API_KEY'),model=setting('GEMINI_MODEL'))
                    if res['auto_committed']: flash('Saved. Your ledger and stock are up to date.')
                    if res['queued_for_review']: st.warning('Drafts sent to pending review.')
                    st.rerun()
                except Exception as e: error(e)
            if auto_col2.button(t('Extract to Draft'),key='btn_ambient_draft',disabled=not consent):
                try:
                    drafts=ai_parser.parse_media_transaction(media_bytes,mime,setting('GEMINI_API_KEY'),setting('GEMINI_MODEL'),currency=currency)
                    if drafts:
                        new_draft(drafts[0], src=f"Extracted from {mime}")
                        st.rerun()
                except Exception as e: error(e)
        if 'draft' in st.session_state and st.session_state.draft_shop==shop_id:
            draft=st.session_state.draft
            a,b=st.columns([4,1])
            a.subheader(t('Review your transaction'))
            if b.button(t('Discard draft')):
                clear_draft()
                st.rerun()
            st.caption(t('Nothing is saved until you confirm.'))
            if draft.get('clarification_question') or draft.get('missing_fields'):
                st.warning(draft.get('clarification_question') or ', '.join(draft['missing_fields']))
            if draft.get('item_name'): st.info(t('AI item suggestion')+': '+draft['item_name'])
            mismatch=draft.get('currency') not in (None,currency)
            if mismatch: st.error(t('Shop currency differs from the extracted currency. No conversion is available. Discard this draft and correct the source.'))
            if st.session_state.get('latency') is not None: st.caption(f"AI · {st.session_state.latency:.2f}s")
            with st.form('review_'+st.session_state.draft_id):
                l,r=st.columns(2)
                options=['']+kinds
                with l:
                    kind=st.selectbox(t('Transaction type'),options,format_func=lambda k:t(k) if k else t('Choose type'),index=options.index(draft.get('type')) if draft.get('type') in options else 0)
                    matched_pid = next((p['id'] for p in items if p['name'].strip().casefold() == (draft.get('item_name') or '').strip().casefold()), '')
                    p_opts = [''] + [p['id'] for p in items]
                    default_p_idx = p_opts.index(matched_pid) if matched_pid in p_opts else 0
                    product_id=st.selectbox(t('Inventory product'),p_opts,format_func=lambda id:next(p['name'] for p in items if p['id']==id) if id else t('Choose product'),index=default_p_idx)
                    qty=st.text_input(t('Quantity (whole units)'),value=str(draft['quantity']) if draft.get('quantity') is not None else '')
                with r:
                    price=st.text_input(t('Unit price / cost')+f' ({currency})',value=input_number(draft.get('unit_price')))
                    amount=st.text_input(t('Expense amount')+f' ({currency})',value=input_number(draft.get('amount_for_expense')))
                    confirmed_currency=st.checkbox(t('Confirm currency')+f': {currency}')
                st.caption(t('Enter amounts using your selected language’s number format.')+' '+format_decimal(1234.56,locale=language))
                st.caption(t('Blank cost is allowed only for restocks. Expenses ignore product and quantity fields.'))
                note=st.text_input(t('Note'),max_chars=500)
                reviewed=st.checkbox(t('I reviewed the details and authorize this transaction.'))
                x,y=st.columns(2)
                preview=x.form_submit_button(t('Check calculated total'),width='stretch',disabled=mismatch)
                submit=y.form_submit_button(t('Confirm & save'),type='primary',width='stretch',disabled=mismatch)
            if preview or submit:
                try:
                    if mismatch: raise ValueError(t('Shop currency differs from the extracted currency. No conversion is available. Discard this draft and correct the source.'))
                    if kind not in kinds: raise ValueError(t('Choose type'))
                    unit=number(price) if price.strip() and kind!='expense' else None
                    exp=number(amount) if kind=='expense' else None
                    if kind=='sale' and unit is None: raise ValueError('A sale requires a unit price.')
                    q=store.whole(qty,'Quantity',1) if kind!='expense' else None
                    total=minor_units(exp,currency) if kind=='expense' else q*minor_units(unit,currency) if unit is not None else None
                    if total is not None and total>minor_units(100000000,currency): raise ValueError('Transaction total exceeds 100,000,000.')
                    if preview: st.info((t('Calculated total')+': '+fmt(total)+'. '+t('Nothing was saved.')) if total is not None else t('Unknown restock cost. Nothing was saved.'))
                    if submit:
                        if not reviewed or not confirmed_currency: raise ValueError(t('Please review and confirm the transaction and currency.'))
                        saved=store.save_transaction(TOKEN,shop_id,st.session_state.draft_id,kind,currency,product_id,qty,unit,exp,note,st.session_state.draft_source,st.session_state.draft_generation)
                        clear_draft()
                        flash('Saved. Your ledger and stock are up to date.' if saved else 'Already saved — no duplicate was added.')
                except (ValueError,PermissionError,sqlite3.Error) as e: error(e)
    else:
        st.info(t('Your role allows read-only access.'))
        clear_draft()
    shop_summary(
        fmt(sum(r['amount_minor'] for r in rows if r['type']=='sale')),
        fmt(sum(r['amount_minor'] for r in rows if r['type']=='expense')),
        sum(r['type']=='sale' for r in rows),
        format_decimal(sum(p['quantity'] for p in items),locale=language),
        language,
    )
    st.subheader(t('Sales over time'))
    st.caption(t('Daily sales over the last 30 days in the shop timezone. Voided sales are excluded.'))
    sales_chart=sales_over_time_frame(rows,shop['timezone'],currency,language,days=30)
    if sales_chart.iloc[:,0].sum():
        st.line_chart(sales_chart,height=260,width='stretch')
    else:
        st.info(t('No sales to chart in the last 30 days.'))
    st.subheader(t('On your shelves'))
    stock_cards(items,language)
    st.subheader(t('Latest activity'))

if shop and page=='AI Advisor & CFO':
    hero(shop['name'],t('AI Advisor & CFO'),f"{currency} · {shop['timezone']}")
    analytics=store.get_shop_analytics(TOKEN,shop_id)
    k1,k2,k3,k4=st.columns(4)
    k1.metric(t('Sales recorded'),fmt(analytics['sales_total_minor']))
    k2.metric(t('Expenses recorded'),fmt(analytics['expense_total_minor']))
    k3.metric(t('Net Cash Flow'),fmt(analytics['net_cash_minor']))
    k4.metric(t('Units on shelves'),format_decimal(sum(p['quantity'] for p in items),locale=language))
    
    st.subheader(t('Stockout Risk & Runway Radar'))
    urgent_items=[r for r in analytics['inventory_runway'] if r['urgent']]
    if urgent_items:
        st.warning(f"⚠️ {len(urgent_items)} product(s) near threshold or running out soon!")
        st.dataframe(urgent_items,hide_index=True,width='stretch')
    else:
        st.success(t("All tracked inventory levels are above alert thresholds."))

    st.subheader(t('Suggested restocks'))
    st.caption(t('Rule: cover 14 days of recent average sales, while meeting the shop minimum stock threshold. Guidance only; this is not a demand forecast.'))
    restock_rows=[]
    for suggestion in analytics['restock_recommendations']:
        quantity=suggestion['suggested_quantity']
        note=t('Not enough recent sales to suggest a quantity') if quantity is None else t('Based on recent sales')
        restock_rows.append({
            t('Product'): suggestion['name'],
            t('On hand'): suggestion['current_stock'],
            t('Min. threshold'): suggestion['threshold'],
            t('Avg. sold/day'): format_decimal(suggestion['daily_velocity'],locale=language),
            t('Estimated days left'): suggestion['days_left'] if suggestion['days_left'] is not None else t('Unknown'),
            t('Target stock'): suggestion['target_stock'] if suggestion['target_stock'] is not None else t('Review stock'),
            t('Suggested order'): quantity if quantity is not None else t('Review stock'),
            t('Why'): note,
        })
    if restock_rows:
        st.dataframe(restock_rows,hide_index=True,width='stretch')
    else:
        st.info(t('No restock suggestion from recent sales and current stock.'))
        
    st.divider()
    st.subheader(t('Daily Executive Briefing'))
    st.caption(t("Generate an autonomous, AI-synthesized daily briefing of today's shop performance with proactive recommendations."))
    if st.button(t('Generate Executive Briefing'),type='primary',disabled=not ready):
        with st.spinner(t('Preparing your draft…')):
            try:
                briefing=ai_cfo.generate_executive_briefing(TOKEN,shop_id,setting('GEMINI_API_KEY'),setting('GEMINI_MODEL'),language=language)
                st.session_state.current_briefing=briefing
            except Exception as e: error(e)
    if 'current_briefing' in st.session_state:
        st.markdown(st.session_state.current_briefing)
        st.code(st.session_state.current_briefing,language=None)
        
    st.divider()
    st.subheader(t('Consult CFO'))
    st.caption(t('Ask any question about your revenue, expenses, product velocity, or margins.'))
    prompts=[
        "Which products generated the highest sales?",
        "Which items are at risk of running out first?",
        "Give me 3 strategies to improve our cash flow.",
        "How do our total expenses compare to total sales?"
    ]
    sel_prompt=st.selectbox(t('Quick questions'),['-- Select a question --']+prompts)
    custom_q=st.text_input(t('Or ask your own question:'),value=sel_prompt if sel_prompt!='-- Select a question --' else '')
    if st.button(t('Consult CFO'),type='primary',key='btn_consult_cfo',disabled=not (ready and custom_q.strip())):
        with st.spinner(t('Preparing your draft…')):
            try:
                answer=ai_cfo.ask_cfo(TOKEN,shop_id,custom_q,setting('GEMINI_API_KEY'),setting('GEMINI_MODEL'),language=language)
                st.session_state.cfo_answer=answer
            except Exception as e: error(e)
    if 'cfo_answer' in st.session_state:
        st.info(st.session_state.cfo_answer)

if shop and page=='Inventory':
    hero(shop['name'],t('Keep your stock in step.'),t('Opening balances are setup quantities, not purchases. Record later additions as restocks.'))
    stock_cards(items,language)
    if 'inventory' in allowed:
        l,r=st.columns(2)
        with l:
            with st.form('product'):
                st.subheader(t('Add a product'))
                name=st.text_input(t('Product name'),max_chars=120)
                opening=st.number_input(t('Opening quantity'),min_value=0,max_value=100000000,step=1)
                threshold=st.number_input(t('Low-stock threshold'),min_value=0,max_value=100000000,value=5,step=1)
                if st.form_submit_button(t('Add a product'),type='primary'):
                    try:
                        store.add_product(TOKEN,shop_id,name,opening,threshold)
                        flash('Product added.')
                    except (ValueError,PermissionError,sqlite3.Error) as e: error(e)
        with r:
            if items:
                with st.form('threshold'):
                    selected=st.selectbox(t('Product'),[p['id'] for p in items],format_func=lambda id:next(p['name'] for p in items if p['id']==id))
                    threshold=st.number_input(t('Low-stock threshold'),min_value=0,max_value=100000000,step=1,value=5,key='new_threshold')
                    if st.form_submit_button(t('Update threshold')):
                        try:
                            store.set_threshold(TOKEN,shop_id,selected,threshold)
                            flash('Stock alert updated.')
                        except (ValueError,PermissionError,sqlite3.Error) as e: error(e)
    else: st.info(t('Your role allows read-only access.'))

if shop and page in ('Ledger','Record & overview'):
    if page=='Ledger': hero(shop['name'],t('Every record, in one place.'),f"{currency} · {shop['timezone']}")
    if rows:
        visible_rows=rows
        if page=='Ledger':
            a,b=st.columns([1,2])
            available_types = ['sale','expense','restock','void']
            selected=a.multiselect(t('Transaction types'),available_types,default=['sale','expense','restock','void'],format_func=t)
            search=b.text_input(t('Search product, note or source')).casefold()
            visible_rows=[r for r in rows if r['type'] in selected and (not search or any(search in (r.get(k) or '').casefold() for k in ['item_name','note','source_text']))]
        else: visible_rows=rows[:8]
        frame=ledger_frame(visible_rows,shop['timezone'],language)
        if page=='Record & overview':
            activity_table(visible_rows,shop['timezone'],language)
        else:
            st.dataframe(frame.drop(columns=[t('Source'),t('Record ID'),'Created by'],errors='ignore'),hide_index=True,width='stretch')
        st.download_button(t('Download full ledger'),csv_bytes(ledger_frame(rows,display=False)),f'saysale-{shop_id}.csv','text/csv')
        st.caption(t('Unknown restock amounts are blank, not zero. No currency conversion is performed.'))
        if page=='Ledger':
            with st.expander(t('Source')): st.dataframe(frame,hide_index=True,width='stretch')
            
            if 'void' in allowed:
                with st.expander(f"🔄 {t('Void / Reverse Transaction')}"):
                    st.caption(t('Creates an automatic pre-mutation snapshot, reverses shelf inventory, and logs an audited void record.'))
                    active_candidates = [r for r in rows if r['type'] in ('sale','expense','restock') and '(Voided)' not in (r.get('note') or '')]
                    if active_candidates:
                        with st.form('void_form'):
                            void_target = st.selectbox(t('Select transaction to void'), [r['id'] for r in active_candidates],
                                format_func=lambda tid: f"{next(r['created_at'][:16] for r in active_candidates if r['id']==tid)} · {t(next(r['type'] for r in active_candidates if r['id']==tid)).upper()} · {next(r['item_name'] or t('General expense') for r in active_candidates if r['id']==tid)} (ID: {tid[:12]}…)")
                            void_reason = st.text_input(t('Reason for voiding / reversal (e.g. customer return, billing error)'), max_chars=200)
                            confirm_void = st.checkbox(t('I confirm reversing this transaction and adjusting stock.'))
                            if st.form_submit_button(t('Void transaction'), type='primary'):
                                if not confirm_void:
                                    st.error(t('Please confirm that you want to void this transaction.'))
                                else:
                                    try:
                                        res = store.void_transaction(TOKEN, shop_id, void_target, void_reason)
                                        clear_draft()
                                        flash(f"Transaction voided. Pre-mutation snapshot saved ({res['snapshot_id']}).")
                                    except Exception as e: error(e)
                    else:
                        st.info(t('No active non-voided transactions available to void.'))
            
            with st.expander(f"📸 {t('Ledger Snapshots & Point-in-Time History')}"):
                st.caption(t('Immutable audit snapshots taken automatically before ledger reversals, or manually created.'))
                if 'audit' in allowed:
                    snap_col1, snap_col2 = st.columns([3, 1])
                    with snap_col1:
                        snap_note = st.text_input(t('Manual snapshot note'), placeholder=t('e.g. Month-end inventory audit'), key='manual_snap_note')
                    with snap_col2:
                        if st.button(t('Create snapshot now'), key='btn_create_snap'):
                            try:
                                new_snap_id = store.snapshot_ledger(TOKEN, shop_id, trigger_action='manual_snapshot', trigger_reason=snap_note)
                                flash(f"Snapshot created: {new_snap_id}")
                            except Exception as e: error(e)
                snapshots = store.list_snapshots(TOKEN, shop_id)
                if snapshots:
                    snap_rows = []
                    for s in snapshots:
                        snap_rows.append({
                            t('Snapshot ID'): s['id'],
                            t('Time'): local_time(s['created_at'], shop['timezone']),
                            t('Action'): s['trigger_action'],
                            t('Reason'): s['trigger_reason'],
                            t('Created by'): s.get('user_name') or s['created_by'][:8]
                        })
                    st.dataframe(snap_rows, hide_index=True, width='stretch')
                else:
                    st.info(t('No snapshots recorded yet.'))
    else: st.info(t('No records yet. Confirm your first transaction to begin.'))

if shop and page=='Team':
    hero(shop['name'],t('Team'),t('Members'))
    if 'team' not in allowed: st.warning(t('Your role cannot perform this action.'))
    else:
        try:
            members=store.team(TOKEN,shop_id)
            st.dataframe([{t('Name'):m['name'],t('Email'):m['email'],t('Role'):t(m['role'])} for m in members],hide_index=True,width='stretch')
            l,r=st.columns(2)
            with l:
                with st.form('invite'):
                    st.subheader(t('Invite a teammate'))
                    email=st.text_input(t('Email'),max_chars=254)
                    invite_role=st.selectbox(t('Role'),['manager','clerk','viewer'],format_func=t)
                    if st.form_submit_button(t('Create invitation'),type='primary'):
                        try:
                            code=store.create_invite(TOKEN,shop_id,email,invite_role)
                            st.session_state.invite_code=code
                            smtp_cfg = email_service.get_smtp_config()
                            if smtp_cfg['configured']:
                                try:
                                    sent = email_service.send_invitation_email(
                                        to_email=email,
                                        shop_name=shop['name'],
                                        role=invite_role,
                                        inviter_name=user['name'],
                                        invite_code=code,
                                        config=smtp_cfg
                                    )
                                    if sent:
                                        st.session_state.invite_email_sent = email
                                except Exception as smtp_err:
                                    logging.getLogger(__name__).warning("SMTP invite send failed: %s", smtp_err)
                        except (ValueError,PermissionError,sqlite3.Error) as e: error(e)
                if 'invite_code' in st.session_state:
                    if st.session_state.pop('invite_email_sent', None):
                        st.success(f"📧 {t('Invitation email sent via SMTP to')} {email}!")
                    st.info(t('Copy this one-time code and share it securely with the named person. It expires in 48 hours.'))
                    st.code(st.session_state.invite_code,language=None)
                    if st.button(t('Close')):
                        st.session_state.pop('invite_code',None)
                        st.rerun()
            with r:
                editable=[m for m in members if m['role']!='owner']
                if editable:
                    with st.form('member'):
                        member=st.selectbox(t('Manage member'),[m['id'] for m in editable],format_func=lambda id:next(m['email'] for m in editable if m['id']==id))
                        new_role=st.selectbox(t('Role'),['manager','clerk','viewer'],format_func=t,key='member_role')
                        update=st.form_submit_button(t('Change role'))
                        remove=st.form_submit_button(t('Remove member'))
                        if update or remove:
                            try:
                                if remove: store.remove_member(TOKEN,shop_id,member)
                                else: store.change_role(TOKEN,shop_id,member,new_role)
                                flash('Member removed.' if remove else 'Member updated.')
                            except (ValueError,PermissionError,sqlite3.Error) as e: error(e)
            invites=store.pending_invites(TOKEN,shop_id)
            if invites:
                st.subheader(t('Pending invitations'))
                for invite in invites:
                    l,r=st.columns([4,1])
                    l.write(f"{invite['email']} · {t(invite['role'])}")
                    if r.button(t('Revoke invitation'),key='revoke_'+invite['email']):
                        store.revoke_invite(TOKEN,shop_id,invite['email'])
                        flash('Invitation revoked.')
        except (PermissionError,sqlite3.Error) as e: error(e)

if shop and page=='Settings':
    hero(shop['name'],t('Shop settings'),f'{currency} · {shop["timezone"]}')
    if 'settings' in allowed:
        with st.form('shop_settings'):
            name=st.text_input(t('Shop name'),value=shop['name'],max_chars=100)
            countries=sorted(COUNTRIES)
            country=st.selectbox(t('Country / region'),countries,index=countries.index(shop['country']),format_func=lambda c:Locale(language).territories.get(c,c))
            timezone=st.selectbox(t('Timezone'),TIMEZONES,index=TIMEZONES.index(shop['timezone']))
            st.caption(t('Currency is fixed for this shop to protect existing records. Create a separate shop for another currency.'))
            if st.form_submit_button(t('Save settings')):
                try:
                    store.update_shop(TOKEN,shop_id,name,country,timezone)
                    flash('Settings saved.')
                except (ValueError,PermissionError,sqlite3.Error) as e: error(e)
        with st.expander(t('Demo data')):
            st.warning(t('Reset deletes this shop’s transactions and products only. Members and audit history remain.'))
            agreed=st.checkbox(t('I understand this deletes this shop’s ledger and stock.'))
            if st.button(t('Reset this shop'),disabled=not agreed):
                try:
                    store.reset_demo(TOKEN,shop_id)
                    clear_draft()
                    flash('Demo shop reset.')
                except (PermissionError,sqlite3.Error) as e: error(e)
        with st.expander(t('Inbound Webhook & Automation Simulator')):
            st.caption('Configure a real inbound endpoint. All webhook transactions enter Pending review; none are auto-posted.')
            webhook_secret_key = f'new_webhook_secret_{shop_id}'
            if st.button('Generate / rotate webhook secret', key='webhook_secret_rotate'):
                try:
                    st.session_state[webhook_secret_key] = store.create_webhook_secret(TOKEN, shop_id)
                except (PermissionError, sqlite3.Error) as e:
                    error(e)
            if st.session_state.get(webhook_secret_key):
                st.warning('Copy this secret now. It is shown only in this session and cannot be retrieved later.')
                st.code(st.session_state[webhook_secret_key])
            endpoint = f"POST /webhooks/{shop_id}/transactions"
            st.code(endpoint)
            st.caption('Header: X-SaySale-Webhook-Token. JSON: {"event_id":"provider-event-id","source_channel":"external_pos","text":"Sold 2 cooking oils at 25 each"}')
            if st.button('Revoke webhook secret', key='webhook_secret_revoke'):
                try:
                    store.revoke_webhook_secret(TOKEN, shop_id)
                    st.session_state.pop(webhook_secret_key, None)
                    flash('Webhook secret revoked.')
                except (PermissionError, sqlite3.Error) as e:
                    error(e)
            try:
                webhook_events = store.list_webhook_events(TOKEN, shop_id)
                if webhook_events:
                    st.dataframe(webhook_events, hide_index=True, width='stretch')
                    for webhook_event in webhook_events:
                        if webhook_event['status'] == 'failed' and st.button('Retry failed event', key=f"retry_webhook_{webhook_event['id']}"):
                            if store.retry_webhook_event(TOKEN, shop_id, webhook_event['id']):
                                flash('Webhook event queued for retry.')
                                st.rerun()
            except (PermissionError, sqlite3.Error) as e:
                error(e)
            st.divider()
            st.caption(t('Simulator only: use this to test the pending-review workflow locally.'))
            wh_text=st.text_input(t('Simulated inbound message'),value=f'Sold 2 cooking oils at 25 {currency} each')
            wh_channel=st.selectbox(t('Channel'),['whatsapp','sms','external_pos'])
            if st.button(t('Simulate Inbound Event'),disabled=not ready):
                try:
                    res=ai_automation.process_inbound_record(
                        shop_id=shop_id,user_token=TOKEN,raw_text=wh_text,source_channel=wh_channel,
                        api_key=setting('GEMINI_API_KEY'),model=setting('GEMINI_MODEL'),auto_commit_threshold=1.01)
                    if res['auto_committed']: flash('Saved. Your ledger and stock are up to date.')
                    if res['queued_for_review']: st.warning('Drafts sent to pending review.')
                    st.rerun()
                except Exception as e: error(e)
        with st.expander(f"📧 {t('SMTP Email Delivery Settings & Test')}"):
            smtp_status = email_service.get_smtp_config()
            if smtp_status['configured']:
                st.success(f"✅ {t('SMTP configured')} ({smtp_status['host']}:{smtp_status['port']}, sender: {smtp_status['sender']})")
            else:
                st.info(t('SMTP is currently unconfigured. Invitations will display codes on-screen. Configure SMTP via environment variables or .streamlit/secrets.toml.'))
            test_target = st.text_input(t('Send test email to:'), value=user['email'], key='test_smtp_email')
            if st.button(t('Send Test Email'), key='btn_send_test_email', disabled=not smtp_status['configured']):
                try:
                    ok = email_service.send_email(
                        to_email=test_target,
                        subject=f"SaySale SMTP Test — {shop['name']}",
                        body_text=f"This is a test email confirming that SMTP is working properly for {shop['name']} on SaySale.",
                        body_html=f"<p>This is a test email confirming that <strong>SMTP is working properly</strong> for <strong>{shop['name']}</strong> on SaySale.</p>",
                        config=smtp_status,
                        sender_name=shop['name']
                    )
                    if ok:
                        flash('Test email sent successfully!')
                except Exception as e:
                    error(e)
    else: st.info(t('Your role cannot perform this action.'))
    if 'audit' in allowed:
        with st.expander(t('Audit trail')):
            try: st.dataframe(store.audit(TOKEN,shop_id),hide_index=True,width='stretch')
            except (PermissionError,sqlite3.Error) as e: error(e)

st.markdown('<div class="footer">SAYSALE &nbsp; / &nbsp; '+escape(t('Prototype · Synthetic data only · Not certified accounting software.'))+'</div>',unsafe_allow_html=True)
