"""CSV / XLSX import service."""
from __future__ import annotations
import csv, hashlib, io, re, unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime
from uuid import uuid4

try:
    import openpyxl; _HAS_OPX = True
except ImportError:
    _HAS_OPX = False

from models import BankStatement, Invoice, Settlement

_ID_ALIASES        = ["id","settlement_id","txn_id","transaction_id","invoice_id","invoice_number","ref_id","sl_no","sno","sr"]
_REFERENCE_ALIASES = ["reference","utr","utr_number","payment_reference","payment_ref","transaction_reference","txn_ref","settlement_reference","ref","narration","description","remarks"]
_AMOUNT_ALIASES    = ["amount","transaction_amount","settled_amount","net_amount","value","credit","debit","gross_amount","total_amount","invoice_amount","net","gross"]
_VENDOR_ALIASES    = ["vendor","merchant","merchant_name","counterparty","beneficiary","party_name","vendor_name","payee","payer","account_name","narration"]
_DATE_ALIASES      = ["date","transaction_date","settlement_date","payment_date","value_date","txn_date","invoice_date","due_date","posting_date","entry_date"]
_INV_ALIASES       = ["invoice_number","invoice_no","inv_no","inv_number","bill_number","bill_no"]
_FEE_ALIASES       = ["fee","charges","processing_fee","txn_fee"]
_TAX_ALIASES       = ["tax","gst","igst","cgst","sgst","tds"]

@dataclass
class ColumnMap:
    id_col: str|None=None; reference_col: str|None=None; amount_col: str|None=None
    vendor_col: str|None=None; date_col: str|None=None; invoice_num_col: str|None=None
    fee_col: str|None=None; tax_col: str|None=None; ambiguous: list=field(default_factory=list)
    def as_dict(self):
        return {"id":self.id_col,"reference":self.reference_col,"amount":self.amount_col,
                "vendor":self.vendor_col,"date":self.date_col,"invoice_num":self.invoice_num_col,
                "fee":self.fee_col,"tax":self.tax_col,"ambiguous":self.ambiguous}

@dataclass
class FileReport:
    file_type:str; filename:str; file_hash:str; total_rows:int; valid_rows:int
    rejected:list; mapping:dict; preview:list; columns:list; warnings:list

@dataclass
class ImportSession:
    import_id:str; batch_id:str; settlements:FileReport|None; bank:FileReport|None
    invoices:FileReport|None; models_s:list; models_b:list; models_i:list; is_complete:bool

_sessions: dict = {}

def get_session(iid): return _sessions.get(iid)

_FML = re.compile(r"^[=+\-@|]")
def _safe(v):
    v=str(v).strip()
    while _FML.match(v): v=v[1:].strip()
    return v

def _nc(n):
    n=unicodedata.normalize("NFKD",n).encode("ascii","ignore").decode()
    return re.sub(r"[^a-z0-9]","_",n.lower()).strip("_")

def _m(col,aliases):
    nc=_nc(col)
    return any(nc==_nc(a) or nc.startswith(_nc(a)) for a in aliases)

def _detect(cols):
    cm=ColumnMap()
    for c in cols:
        if _m(c,_ID_ALIASES)        and not cm.id_col:          cm.id_col=c
        if _m(c,_REFERENCE_ALIASES) and not cm.reference_col:   cm.reference_col=c
        if _m(c,_AMOUNT_ALIASES)    and not cm.amount_col:       cm.amount_col=c
        if _m(c,_VENDOR_ALIASES)    and not cm.vendor_col:       cm.vendor_col=c
        if _m(c,_DATE_ALIASES)      and not cm.date_col:         cm.date_col=c
        if _m(c,_INV_ALIASES)       and not cm.invoice_num_col:  cm.invoice_num_col=c
        if _m(c,_FEE_ALIASES)       and not cm.fee_col:          cm.fee_col=c
        if _m(c,_TAX_ALIASES)       and not cm.tax_col:          cm.tax_col=c
    used={}
    for role,val in [("id",cm.id_col),("reference",cm.reference_col),("amount",cm.amount_col),("vendor",cm.vendor_col),("date",cm.date_col)]:
        if val:
            if val in used: cm.ambiguous.append(f"{val!r} matched both {used[val]!r} and {role!r}")
            used[val]=role
    return cm

def _pa(raw):
    c=re.sub(r"[₹$€£,\s]","",str(raw).strip())
    if not c: return None
    try: return float(c)
    except: return None

_DFMTS=["%Y-%m-%d","%d-%m-%Y","%m/%d/%Y","%d/%m/%Y","%d-%b-%Y","%d %b %Y","%b %d, %Y","%Y%m%d","%d/%m/%y","%m/%d/%y","%d-%m-%y"]
def _pd(raw):
    for f in _DFMTS:
        try: return datetime.strptime(str(raw).strip(),f).date()
        except: pass
    return None

def _read(content,filename):
    ext=filename.rsplit(".",1)[-1].lower()
    if ext in ("xlsx","xls"):
        if not _HAS_OPX: raise ValueError("openpyxl not installed")
        wb=openpyxl.load_workbook(io.BytesIO(content),read_only=True,data_only=True)
        ws=wb.active; rows=list(ws.iter_rows(values_only=True))
        if not rows: return []
        hdrs=[str(h or "").strip() for h in rows[0]]
        return [{hdrs[i]:str(cell or "") for i,cell in enumerate(row)} for row in rows[1:]]
    text=content.decode("utf-8-sig",errors="replace")
    return list(csv.DictReader(io.StringIO(text)))

def _fhash(b): return hashlib.sha256(b).hexdigest()[:16]

def _parse_s(raw,cm,bid):
    valid,rej,prev,seen=[],[],[],set()
    today=date.today()
    for i,row in enumerate(raw,2):
        sr={k:_safe(v) for k,v in row.items()}; errs=[]
        sid=sr.get(cm.id_col or "",""  ) if cm.id_col else ""
        sid=sid or f"CSV-S-{i:05d}"
        if sid in seen: errs.append("duplicate_id")
        seen.add(sid)
        ref=sr.get(cm.reference_col or "",sid) if cm.reference_col else sid
        amt=_pa(sr.get(cm.amount_col or "","")) if cm.amount_col else None
        if amt is None: errs.append("invalid_amount")
        elif amt<=0: errs.append("non_positive_amount")
        vendor=sr.get(cm.vendor_col or "","Unknown") if cm.vendor_col else "Unknown"
        raw_d=sr.get(cm.date_col or "","") if cm.date_col else ""
        txn_d=_pd(raw_d) if raw_d else today
        if raw_d and txn_d is None: errs.append(f"invalid_date:{raw_d!r}")
        fee=_pa(sr.get(cm.fee_col or "","0")) if cm.fee_col else 0.0
        tax=_pa(sr.get(cm.tax_col or "","0")) if cm.tax_col else 0.0
        inv=sr.get(cm.invoice_num_col or "","") if cm.invoice_num_col else ""
        if errs:
            rej.append({"row":i,"reason":"; ".join(errs),"data":dict(list(sr.items())[:4])})
            continue
        valid.append(Settlement(settlement_id=f"CSV-{bid[-6:]}-S{i:05d}",amount=round(amt,2),
            currency="INR",date=txn_d,vendor_name_raw=vendor,reference_id=ref,
            fee=round(fee or 0,2),tax=round(tax or 0,2),batch_id=bid,invoice_number=inv))
        if len(prev)<5: prev.append(dict(list(sr.items())[:6]))
    return valid,rej,prev

def _parse_b(raw,cm,bid):
    valid,rej,prev,seen=[],[],[],set()
    today=date.today()
    for i,row in enumerate(raw,2):
        sr={k:_safe(v) for k,v in row.items()}; errs=[]
        raw_id=sr.get(cm.id_col or "",""  ) if cm.id_col else ""
        tid=raw_id or f"CSV-B-{i:05d}"
        if tid in seen: errs.append("duplicate_id")
        seen.add(tid)
        ref=sr.get(cm.reference_col or "",tid) if cm.reference_col else tid
        nar=sr.get(cm.vendor_col or cm.reference_col or "","") if (cm.vendor_col or cm.reference_col) else ""
        amt=_pa(sr.get(cm.amount_col or "","")) if cm.amount_col else None
        if amt is None: errs.append("invalid_amount")
        elif amt<=0: errs.append("non_positive_amount")
        raw_d=sr.get(cm.date_col or "","") if cm.date_col else ""
        txn_d=_pd(raw_d) if raw_d else today
        if raw_d and txn_d is None: errs.append(f"invalid_date:{raw_d!r}")
        if errs:
            rej.append({"row":i,"reason":"; ".join(errs),"data":dict(list(sr.items())[:4])})
            continue
        valid.append(BankStatement(txn_id=f"CSV-{bid[-6:]}-B{i:05d}",amount=round(amt,2),
            date=txn_d,narration_raw=nar or ref,reference=ref,currency="INR",batch_id=bid))
        if len(prev)<5: prev.append(dict(list(sr.items())[:6]))
    return valid,rej,prev

def _parse_i(raw,cm,bid):
    valid,rej,prev,seen=[],[],[],set()
    today=date.today()
    for i,row in enumerate(raw,2):
        sr={k:_safe(v) for k,v in row.items()}; errs=[]
        raw_id=sr.get(cm.id_col or "",""  ) if cm.id_col else ""
        raw_inv=sr.get(cm.invoice_num_col or "","") if cm.invoice_num_col else raw_id
        iid=raw_id or raw_inv or f"CSV-I-{i:05d}"
        if iid in seen: errs.append("duplicate_id")
        seen.add(iid)
        vendor=sr.get(cm.vendor_col or "","Unknown") if cm.vendor_col else "Unknown"
        amt=_pa(sr.get(cm.amount_col or "","")) if cm.amount_col else None
        if amt is None: errs.append("invalid_amount")
        elif amt<=0: errs.append("non_positive_amount")
        raw_d=sr.get(cm.date_col or "","") if cm.date_col else ""
        due_d=_pd(raw_d) if raw_d else today
        if raw_d and due_d is None: errs.append(f"invalid_date:{raw_d!r}")
        if errs:
            rej.append({"row":i,"reason":"; ".join(errs),"data":dict(list(sr.items())[:4])})
            continue
        valid.append(Invoice(invoice_id=f"CSV-{bid[-6:]}-I{i:05d}",amount=round(amt,2),
            currency="INR",due_date=due_d,vendor_name_raw=vendor,
            invoice_number=raw_inv or iid,batch_id=bid))
        if len(prev)<5: prev.append(dict(list(sr.items())[:6]))
    return valid,rej,prev

MAX_BYTES=10*1024*1024; MAX_ROWS=10_000

def process_upload(sb,sn,bb,bn,ib,inp):
    iid=uuid4().hex[:12]; bid=f"IMPORT-{iid}"
    def chk(b,n):
        if len(b)>MAX_BYTES: raise ValueError(f"{n}: exceeds 10 MB")
    def proc(content,fname):
        raw=_read(content,fname)
        if not raw: raise ValueError(f"{fname}: empty")
        raw=raw[:MAX_ROWS]; cols=list(raw[0].keys())
        cm=_detect(cols); warns=[]
        if not cm.amount_col: warns.append("Amount column not detected")
        if not cm.date_col:   warns.append("Date column not detected — using today")
        warns.extend(cm.ambiguous)
        return raw,cols,cm,warns,_fhash(content)
    s_rpt=b_rpt=i_rpt=None; ms,mb,mi=[],[],[]
    if sb:
        chk(sb,sn or "settlements"); raw,cols,cm,warns,fh=proc(sb,sn or "settlements.csv")
        valid,rej,prev=_parse_s(raw,cm,bid)
        s_rpt=FileReport("settlements",sn or "settlements.csv",fh,len(raw),len(valid),rej[:50],cm.as_dict(),prev,cols,warns); ms=valid
    if bb:
        chk(bb,bn or "bank"); raw,cols,cm,warns,fh=proc(bb,bn or "bank.csv")
        valid,rej,prev=_parse_b(raw,cm,bid)
        b_rpt=FileReport("bank",bn or "bank.csv",fh,len(raw),len(valid),rej[:50],cm.as_dict(),prev,cols,warns); mb=valid
    if ib:
        chk(ib,inp or "invoices"); raw,cols,cm,warns,fh=proc(ib,inp or "invoices.csv")
        valid,rej,prev=_parse_i(raw,cm,bid)
        i_rpt=FileReport("invoices",inp or "invoices.csv",fh,len(raw),len(valid),rej[:50],cm.as_dict(),prev,cols,warns); mi=valid
    sess=ImportSession(iid,bid,s_rpt,b_rpt,i_rpt,ms,mb,mi,bool(sb and bb and ib))
    _sessions[iid]=sess; return sess

def _rpt(r):
    if r is None: return None
    return {"file_type":r.file_type,"filename":r.filename,"file_hash":r.file_hash,
            "total_rows":r.total_rows,"valid_rows":r.valid_rows,"rejected_count":len(r.rejected),
            "rejected":r.rejected[:10],"mapping":r.mapping,"preview":r.preview,
            "columns":r.columns,"warnings":r.warnings}

def session_summary(s):
    return {"import_id":s.import_id,"batch_id":s.batch_id,"is_complete":s.is_complete,
            "settlements":_rpt(s.settlements),"bank":_rpt(s.bank),"invoices":_rpt(s.invoices),
            "counts":{"settlements":len(s.models_s),"bank":len(s.models_b),"invoices":len(s.models_i)},
            "warnings":[*(s.settlements.warnings if s.settlements else []),
                        *(s.bank.warnings if s.bank else []),
                        *(s.invoices.warnings if s.invoices else [])]}
