"""Filtered receivable/payable reporting with separate cash and settlement measures.

ERPNext owns ledger selection and return/revaluation routing. Cash is selected by
that same ledger scope, but bank legs are read in full so account/cost-centre
filters cannot accidentally remove the other side of a payment.
"""
from collections import defaultdict
from copy import deepcopy

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, nowdate
from erpnext.accounts.report.accounts_receivable.accounts_receivable import ReceivablePayableReport


def read_all(doctype, fields, filters):
    return frappe.get_list(doctype, fields=fields, filters=filters, limit_page_length=0)


def project_share(invoice, items, project=None, unassigned=False):
    if not project and not unassigned:
        return 1.0
    target = None if unassigned else project
    if invoice.get('project'):
        return float(invoice.project == target)
    weights = defaultdict(float)
    for item in items:
        weights[item.get('project') or None] += abs(flt(item.get('base_net_amount')))
    total = sum(weights.values())
    return weights[target] / total if total else float(target is None)


def cash_shares(cash, movements):
    sign = 1 if cash > 0 else -1
    weights = {p: max(0, sign * v) for p, v in movements.items()}
    total = sum(weights.values())
    return {p: sign * min(abs(cash), total) * v / total for p, v in weights.items() if v} if total else {}


def key(row):
    return (row.get('party_type'), row.get('party'), row.get('party_account') or row.get('account'),
            row.get('voucher_type'), row.get('voucher_no'))


class Ledger(ReceivablePayableReport):
    def set_defaults(self):
        super().set_defaults()
        self.return_entries = {}

    def fetch_ple_in_buffered_cursor(self):
        self.entries = self.ple_query.run(as_dict=True)
        for ple in self.entries:
            self.init_voucher_balance(ple)
        for ple in self.entries:
            self.update_voucher_balance(ple)
    fetch_ple_in_unbuffered_cursor = fetch_ple_in_buffered_cursor

    def build_data(self):
        self.data = []
        self.selected_entries = []
        for ple in self.entries:
            row = self.get_voucher_balance(ple)
            if row is None:
                continue
            self.selected_entries.append(ple)
            is_settlement = ple.voucher_type == 'Payment Entry' or (
                self.is_invoice(ple) and ple.voucher_no == ple.against_voucher_no and ple.amount < 0
                and not self.invoice_details.get(ple.voucher_no,{}).get('is_return'))
            if self.is_invoice(ple) and ple.voucher_no==ple.against_voucher_no and ple.amount<0 and self.invoice_details.get(ple.voucher_no,{}).get('is_return'):
                value=ple.amount_in_account_currency if self.filters.in_party_currency or self.filters.party_account else ple.amount
                row['_return_face']=flt(row.get('_return_face'))-flt(value)
            if is_settlement:
                amount = ple.amount_in_account_currency if self.filters.in_party_currency or self.filters.party_account else ple.amount
                row['_allocated'] = flt(row.get('_allocated')) - flt(amount)
        for row in self.voucher_balance.values():
            row.outstanding = flt(row.invoiced - row.paid - row.credit_note, self.currency_precision)
            row.outstanding_in_account_currency=flt(row.invoiced_in_account_currency-row.paid_in_account_currency-row.credit_note_in_account_currency,self.currency_precision)
            row.invoice_grand_total = row.invoiced
            row.currency = row.account_currency if self.filters.in_party_currency or self.filters.party_account else self.company_currency
            if any(abs(flt(row.get(k))) > 0.000001 for k in ['invoiced','paid','credit_note','outstanding']) or (self.filters.for_revaluation_journals and abs(row.outstanding_in_account_currency)>.000001):
                self.data.append(row)

    def get_invoice_details(self):
        # Explicit unlimited paging: metadata must not disappear after the first page.
        self.invoice_details = frappe._dict()
        for dt, extra in [('Sales Invoice',['po_no','sales_partner']), ('Purchase Invoice',['bill_no','bill_date']),
                          ('Journal Entry',['bill_no','bill_date'])]:
            if dt == 'Sales Invoice' and self.account_type != 'Receivable':
                continue
            if dt == 'Purchase Invoice' and self.account_type != 'Payable':
                continue
            if not frappe.has_permission(dt, 'read'):
                continue
            for d in read_all(dt, ['name','due_date'] + extra + (['is_return'] if dt!='Journal Entry' else []),
                              {'company':self.filters.company,'posting_date':['<=',self.filters.report_date],'docstatus':1}):
                self.invoice_details[d.name] = d
        if self.filters.show_sales_person and self.account_type == 'Receivable':
            names = list(self.invoice_details)
            if names:
                for d in frappe.get_all('Sales Team', fields=['parent','sales_person'],
                                        filters={'parenttype':'Sales Invoice','parent':['in',names]}):
                    self.invoice_details[d.parent].setdefault('sales_team',[]).append(d.sales_person)


def split_terms(row, schedules):
    """Allocate the as-of ledger settlement FIFO, never today's schedule paid_amount."""
    schedules = sorted(schedules, key=lambda d: (str(d.due_date), d.get('idx') or 0))
    total = sum(max(0, flt(d.base_payment_amount)) for d in schedules)
    if not total or row.invoiced <= 0:
        return [row]
    result = []
    paid, credit, allocated = row.paid, row.credit_note, row.allocated
    used = 0
    for index, schedule in enumerate(schedules):
        term = frappe._dict(deepcopy(row))
        term.payment_term = schedule.get('description') or schedule.get('payment_term') or str(index + 1)
        term.due_date = schedule.due_date
        term.invoiced = row.invoiced - used if index == len(schedules)-1 else row.invoiced * max(0,flt(schedule.base_payment_amount))/total
        used += term.invoiced
        term.paid = min(max(paid,0),term.invoiced)
        paid -= term.paid
        term.credit_note = min(max(credit,0),max(0,term.invoiced-term.paid))
        credit -= term.credit_note
        term.allocated = term.paid * row.allocated/row.paid if row.paid else 0
        allocated -= term.allocated
        term.adjustment = term.paid-term.allocated
        term.outstanding = term.invoiced-term.paid-term.credit_note
        result.append(term)
    if abs(paid)+abs(credit) > .000001:
        extra=frappe._dict(deepcopy(row))
        extra.update(payment_term=_('Thanh toán/điều chỉnh ngoài kỳ hạn'), invoiced=0, paid=paid,
                     credit_note=credit,allocated=allocated,adjustment=paid-allocated,outstanding=-paid-credit)
        result.append(extra)
    return result


class PartyReport:
    def __init__(self, filters, account_type):
        self.f = frappe._dict(deepcopy(filters or {}))
        self.kind = account_type
        self.payable = account_type == 'Payable'
        self.default_party = 'Supplier' if self.payable else 'Customer'
        self.invoice_type = 'Purchase Invoice' if self.payable else 'Sales Invoice'
        self.cashfield = 'disbursed' if self.payable else 'received'
        self.cashview = 'Chi tiết chi tiền' if self.payable else 'Chi tiết thu tiền'
        self.f.report_date = getdate(self.f.report_date or nowdate())
        self.f.party_type = self.f.party_type or self.default_party
        self.f.age_as_on = 'Today' if self.f.calculate_ageing_with == 'Today Date' else 'Report Date'
        self.f.ageing_based_on = self.f.ageing_based_on or 'Due Date'
        self.f.range = self.f.range or '30, 60, 90, 120'
        self.f.view = self.f.view or ('Tổng hợp nhà cung cấp' if self.payable else 'Tổng hợp khách hàng')
        for name in ['party','customer_group']:
            value=self.f.get(name)
            if isinstance(value,str) and value:
                self.f[name] = frappe.parse_json(value) if value.lstrip().startswith('[') else [value]
        self.currency_mode = bool(self.f.in_party_currency or self.f.party_account)
        self.project_active = bool(self.f.project or self.f.unassigned_project)
        self.args={'account_type':account_type,'naming_by':['Buying Settings','supp_master_name'] if self.payable else ['Selling Settings','cust_master_name']}

    def run(self):
        if not self.f.company:
            frappe.throw(_('Vui lòng chọn công ty.'))
        frappe.get_doc('Company',self.f.company).check_permission('read')
        frappe.has_permission('GL Entry','read',throw=True)
        if self.f.project and self.f.unassigned_project:
            frappe.throw(_('Chỉ chọn Project hoặc Chưa xác định Project.'))
        if self.f.project:
            frappe.get_doc('Project',self.f.project).check_permission('read')
        allowed_types=frappe.get_all('Party Type',filters={'account_type':self.kind},pluck='name')
        if self.f.party_type not in allowed_types:
            frappe.throw(_('Party Type không thuộc loại công nợ của báo cáo.'))
        party_meta=frappe.get_meta(self.f.party_type)
        namefield={'Customer':'customer_name','Supplier':'supplier_name','Employee':'employee_name'}.get(self.f.party_type)
        fields=['name']+([namefield] if namefield and party_meta.has_field(namefield) else [])
        fields += [field for field in ['customer_group','territory','customer_primary_contact','supplier_group'] if party_meta.has_field(field)]
        parties=read_all(self.f.party_type,fields,{'name':['in',self.f.party]} if self.f.party else {})
        self.parties={p.name:p.get(namefield) or p.name for p in parties}
        self.party_details={p.name:p for p in parties}
        self.company_currency=frappe.get_cached_value('Company',self.f.company,'default_currency')
        self.ledger=self.make_ledger(self.f)
        if not self.parties:
            return self.columns(),[],None,None,None,0
        # A second, broader ledger supplies denominators; it does not widen displayed results.
        baseline=frappe._dict(company=self.f.company,report_date=self.f.report_date,party_type=self.f.party_type,
                              party=list(self.parties),in_party_currency=self.currency_mode,
                              handle_employee_advances=self.f.handle_employee_advances,
                              for_revaluation_journals=self.f.for_revaluation_journals,range=self.f.range)
        self.full=self.make_ledger(baseline)
        self.load_documents()
        self.invoice_rows,self.other_rows=self.build_ledger_rows()
        self.cash_rows=self.build_cash_rows()
        self.enrich_rows(self.invoice_rows+self.other_rows+self.cash_rows)
        data=self.choose_rows()
        currencies={r.currency for r in data if r.get('currency')}
        skip_total=int(len(currencies)>1 or bool(self.f.group_by_party and self.is_detail()))
        if self.f.group_by_party and self.is_detail():
            data=self.subtotals(data)
        message=_('Tiền thực thu/chi và phân bổ công nợ là hai chỉ tiêu riêng. Bộ lọc tài khoản, sổ tài chính, Cost Center và chiều kế toán chọn phần công nợ liên quan; tiền thực thu/chi được lấy một lần theo tỷ lệ phần được chọn. Tiền tệ đối tác được tách riêng theo từng loại tiền. Kỳ hạn dùng số thanh toán đến ngày báo cáo. Hóa đơn nhiều Project phân bổ theo giá trị thuần; Journal Entry nhiều đối tác phân bổ tiền theo tỷ lệ công nợ.')
        chart=None
        if len(currencies)==1:
            agecols=[c for c in self.columns() if c['fieldname'].startswith('range')]
            chart={'type':'percentage','data':{'labels':[c['label'] for c in agecols], 'datasets':[{'values':[sum(flt(r.get(c['fieldname'])) for r in data if not r.get('bold')) for c in agecols]}]}}
        return self.columns(),data,message,chart,None,skip_total

    def make_ledger(self, filters):
        f=frappe._dict(deepcopy(filters))
        # Project is allocated from invoice lines/receipt references, not a naive PLE filter.
        f.pop('project',None)
        f.group_by_party=0
        f.ignore_accounts=0  # Merge later, within one currency only.
        f.show_future_payments=0  # Actual balances never include future-posted self entries.
        f.party=list(self.parties) or ['__no_accessible_party__']
        ledger=Ledger(f)
        ledger.run(self.args)
        return ledger

    def load_documents(self):
        self.docs={}
        self.items=defaultdict(list)
        self.schedules=defaultdict(list)
        if frappe.has_permission(self.invoice_type,'read'):
            fields=['name',self.default_party.lower(),'project','posting_date','due_date','is_return','return_against',
                    'base_grand_total','base_rounded_total','disable_rounded_total','remarks']
            if self.payable: fields += ['bill_no','bill_date']
            else: fields += ['po_no','sales_partner']
            self.docs={d.name:d for d in read_all(self.invoice_type,fields,
                {'company':self.f.company,'posting_date':['<=',self.f.report_date],'docstatus':1})}
        if self.docs and self.project_active:
            for d in frappe.get_all(self.invoice_type+' Item',fields=['parent','project','base_net_amount'],
                                    filters={'parent':['in',list(self.docs)],'parenttype':self.invoice_type}):
                self.items[d.parent].append(d)
        if self.docs and self.f.based_on_payment_terms:
            for d in frappe.get_all('Payment Schedule',fields=['parent','due_date','payment_term','description','base_payment_amount','idx'],
                                    filters={'parent':['in',list(self.docs)],'parenttype':self.invoice_type}):
                self.schedules[d.parent].append(d)
        self.payments={d.name:d for d in read_all('Payment Entry',
            ['name','party','party_type','project','payment_type','remarks','paid_from','paid_to'],
            {'company':self.f.company,'posting_date':['<=',self.f.report_date],'docstatus':1,
             'party_type':self.f.party_type,'party':['in',list(self.parties)]})} if self.parties and frappe.has_permission('Payment Entry','read') else {}
        self.full_by_voucher=defaultdict(list)
        self.selected_ids={p.name for p in self.ledger.selected_entries}
        for p in self.full.selected_entries:
            self.full_by_voucher[p.voucher_type,p.voucher_no,p.party].append(p)

    def direct_share(self, project):
        if not self.project_active: return 1
        if self.f.unassigned_project: return float(not project)
        return float(project==self.f.project)

    def invoice_share(self, name):
        if name not in self.docs: return 0
        return project_share(self.docs[name],self.items[name],self.f.project,self.f.unassigned_project)

    def build_ledger_rows(self):
        invoices,others=[],[]
        for original in self.ledger.data:
            r=frappe._dict(deepcopy(original))
            if r.party not in self.parties: continue
            r.party_type=self.f.party_type
            r.party_name=self.parties[r.party]
            r.allocated=flt(r.get('_allocated'))
            r.adjustment=r.paid-r.allocated
            r.update(self.ledger.invoice_details.get(r.voucher_no,{}) or {})
            if r.voucher_type==self.invoice_type:
                if r.voucher_no not in self.docs: continue
                doc=self.docs[r.voucher_no]
                factor=self.invoice_share(r.voucher_no)
                r.project=doc.project
                if doc.is_return:
                    # Stand-alone returns are reductions, not new invoices or cash settlements.
                    r.credit_note=flt(r.get('_return_face'))
                    r.invoiced=0
                    r.adjustment=-r.credit_note-r.allocated-r.outstanding
                if self.f.show_remarks: r.remarks=doc.remarks
                if self.f.based_on_payment_terms and not doc.is_return:
                    split=split_terms(r,self.schedules[r.voucher_no])
                else: split=[r]
                for row in split:
                    self.scale(row,factor)
                    if factor: invoices.append(row)
            else:
                payment=self.payments.get(r.voucher_no) if r.voucher_type=='Payment Entry' else None
                factor=self.direct_share(payment.project if payment else r.get('project'))
                r.project=payment.project if payment else r.get('project')
                self.scale(r,factor)
                # Never expose advance reclassification as invoice turnover.
                r.invoiced=r.credit_note=r.allocated=r.adjustment=0
                r.other_balance=max(0,r.outstanding)
                r.advance=max(0,-r.outstanding)
                r.net_balance=r.outstanding
                if factor: others.append(r)
        return invoices,others

    @staticmethod
    def scale(row, factor):
        for field in ['invoiced','paid','credit_note','allocated','adjustment','outstanding','invoice_grand_total','outstanding_in_account_currency']:
            row[field]=flt(row.get(field))*factor

    def cash_parts(self, dtype, name, party, amount):
        """Return selected cash weights by account, preferring original advance legs.

        A payment has both the original advance PLE and later settlement PLEs.
        Taking their sum would count cash twice. Original legs take precedence;
        when filtered out, only selected allocations are attributed to the report.
        """
        entries=self.full_by_voucher[dtype,name,party]
        sign=1 if amount>=0 else -1
        originals=[p for p in entries if p.voucher_type==p.against_voucher_type and p.voucher_no==p.against_voucher_no and p.amount*sign<0]
        allocated=[p for p in entries if p.against_voucher_type==self.invoice_type and p.voucher_no!=p.against_voucher_no and p.amount*sign<0]
        selected_originals=[p for p in originals if p.name in self.selected_ids]
        selected_allocated=[p for p in allocated if p.name in self.selected_ids]
        payment=self.payments.get(name) if dtype=='Payment Entry' else None
        explicit=payment.project if payment else None
        total=max(sum(abs(p.amount) for p in originals),sum(abs(p.amount) for p in allocated),abs(amount))
        if not total: return []
        parts=[]
        if selected_originals:
            scope=sum(abs(p.amount) for p in selected_originals)/total
            if explicit or not self.project_active:
                project_factor=self.direct_share(explicit)
            else:
                matched=sum(abs(p.amount)*self.invoice_share(p.against_voucher_no) for p in selected_allocated)
                residual=max(0,total-sum(abs(p.amount) for p in allocated)) if self.f.unassigned_project else 0
                project_factor=min(1,(matched+residual)/total)
            selected_total=sum(abs(p.amount) for p in selected_originals)
            for p in selected_originals:
                parts.append((p,min(1,scope)*project_factor*abs(p.amount)/selected_total))
        else:
            for p in selected_allocated:
                factor=self.direct_share(explicit) if explicit else self.invoice_share(p.against_voucher_no)
                parts.append((p,abs(p.amount)/total*factor))
        # Cash paid directly on an invoice, or a JE with an Employee Advance target.
        if not parts and dtype==self.invoice_type and name in self.docs:
            selected=[p for p in entries if p.name in self.selected_ids]
            if selected: parts=[(selected[0],self.invoice_share(name))]
        if not parts and dtype=='Journal Entry':
            selected=[p for p in entries if p.name in self.selected_ids and p.amount*sign<0]
            for p in selected:
                if p in selected_allocated: continue
                parts.append((p,min(1,abs(p.amount)/total)*self.direct_share(p.project)))
        return [(p,w) for p,w in parts if w>0]

    def build_cash_rows(self):
        if not self.parties: return []
        accounts={d.name:d for d in read_all('Account',['name','account_type','account_currency'],
                                            {'company':self.f.company,'is_group':0})}
        gls=read_all('GL Entry',['voucher_type','voucher_no','account','party_type','party','debit','credit',
                                'debit_in_account_currency','credit_in_account_currency','posting_date','project','remarks'],
                     {'company':self.f.company,'posting_date':['<=',self.f.report_date],'is_cancelled':0})
        vouchers=defaultdict(list)
        for g in gls: vouchers[g.voucher_type,g.voucher_no].append(g)
        sign=-1 if self.payable else 1
        results=[]
        for (dtype,name),gl in vouchers.items():
            cash=sign*sum(flt(g.debit)-flt(g.credit) for g in gl if accounts.get(g.account,{}).get('account_type') in ('Cash','Bank'))
            if abs(cash)<.000001: continue
            movement=defaultdict(float)
            for g in gl:
                if g.party_type==self.f.party_type: movement[g.party]+=sign*(flt(g.credit)-flt(g.debit))
            amounts=cash_shares(cash,movement)
            if dtype==self.invoice_type and name in self.docs:
                amounts={self.docs[name].get(self.default_party.lower()):cash}
            for party,amount in amounts.items():
                if party not in self.parties: continue
                parts=self.cash_parts(dtype,name,party,amount)
                grouped=defaultdict(float)
                representatives={}
                for p,weight in parts:
                    currency=p.account_currency if self.currency_mode else self.company_currency
                    rate=abs(p.amount_in_account_currency/p.amount) if self.currency_mode and p.amount else 1
                    k=(p.account,currency)
                    grouped[k]+=amount*weight*rate
                    representatives[k]=p
                for (account,currency),value in grouped.items():
                    if abs(value)<.000001: continue
                    p=representatives[account,currency]
                    payment=self.payments.get(name) if dtype=='Payment Entry' else None
                    r=frappe._dict(party_type=self.f.party_type,party=party,party_name=self.parties[party],party_account=account,
                        currency=currency,voucher_type=dtype,voucher_no=name,posting_date=min(g.posting_date for g in gl),
                        project=payment.project if payment else p.project,cost_center=p.cost_center,
                        **{self.cashfield:max(0,value)},refunded=max(0,-value),invoiced=0,credit_note=0,allocated=0,adjustment=0,
                        outstanding=0,paid=0,remaining_payment=0,allocated_payment=0)
                    # As-of ledger balance of the same source voucher, already scoped and projected.
                    for other in self.other_rows:
                        if (other.voucher_type,other.voucher_no,other.party,other.party_account,other.currency)==(dtype,name,party,account,currency):
                            r.remaining_payment-=other.outstanding
                    allocated_entries=[e for e in self.full_by_voucher[dtype,name,party]
                                       if e.name in self.selected_ids and e.against_voucher_type==self.invoice_type
                                       and e.voucher_no!=e.against_voucher_no]
                    for e in allocated_entries:
                        if not self.f.ignore_accounts and e.account!=account and not payment: continue
                        factor=self.direct_share(payment.project) if payment and payment.project else self.invoice_share(e.against_voucher_no)
                        base=-e.amount
                        r.allocated_payment+=base*factor*(abs(p.amount_in_account_currency/p.amount) if self.currency_mode and p.amount else 1)
                    r.outstanding=-r.remaining_payment
                    if self.f.show_remarks: r.remarks=payment.remarks if payment else '\n'.join(dict.fromkeys(g.remarks or '' for g in gl))
                    results.append(r)
        return results

    def enrich_rows(self, rows):
        for r in rows:
            for field in ['customer_group','territory','customer_primary_contact','supplier_group']:
                r[field]=self.party_details.get(r.party,{}).get(field)
            r.setdefault('currency',self.company_currency)
            # Metadata options also work on aggregate rows (joined below).
            if self.f.show_sales_person and r.voucher_type==self.invoice_type:
                r.sales_person=', '.join(self.ledger.invoice_details.get(r.voucher_no,{}).get('sales_team',[]))
            if self.f.show_delivery_notes and r.voucher_type=='Sales Invoice':
                r.delivery_notes=', '.join(sorted(self.ledger.delivery_notes.get(r.voucher_no,[])))
            self.ledger.set_ageing(r)
        if self.f.show_future_payments:
            self.apply_future(rows)

    def apply_future(self, rows):
        # Retain ERPNext's draft/submitted future-payment definition and use its conversion.
        self.ledger.filters.show_future_payments=1
        self.ledger.get_future_payments()
        pools=defaultdict(float);refs=defaultdict(set)
        for (invoice,party),entries in self.ledger.future_payments.items():
            for e in entries:
                if e.party_type!=self.f.party_type: continue
                field='future_amount' if self.currency_mode else 'future_amount_in_base_currency'
                pools[invoice,party]+=flt(e.get(field))
                refs[invoice,party].add(str(e.get('future_ref') or '')+'/'+str(e.future_date))
        # Scope the forecast once per invoice/currency, then allocate FIFO across terms.
        scoped=defaultdict(float);full=defaultdict(float)
        for r in self.invoice_rows:
            scoped[r.voucher_no,r.party,r.currency]+=max(0,r.invoiced)
        for r in self.full.data:
            if r.voucher_type==self.invoice_type:
                cur=r.account_currency if self.currency_mode else self.company_currency
                full[r.voucher_no,r.party,cur]+=max(0,r.invoiced)
        remaining={}
        for r in sorted(rows,key=lambda r:(r.party,str(r.get('due_date') or r.posting_date))):
            k=(r.voucher_no,r.party)
            bucket=(r.voucher_no,r.party,r.currency)
            if bucket not in remaining:
                factor=min(1,scoped[bucket]/full[bucket]) if full[bucket] else self.direct_share(r.project)
                remaining[bucket]=pools[k]*factor
            r.future_amount=min(max(r.outstanding,0),max(remaining[bucket],0))
            remaining[bucket]-=r.future_amount
            r.remaining_balance=r.outstanding-r.future_amount
            r.future_ref=', '.join(sorted(refs[k])) if r.future_amount else ''

    def is_detail(self):
        return self.f.view in ('Chi tiết hóa đơn',self.cashview,'Chi tiết công nợ')

    def measures(self):
        return ['invoiced','credit_note',self.cashfield,'refunded','allocated','adjustment','advance','outstanding',
                'other_balance','net_balance','future_amount','remaining_balance','allocated_payment','remaining_payment'] + ['range0'] + ['range'+str(n) for n in self.ledger.range_numbers]

    def choose_rows(self):
        if self.f.view=='Chi tiết hóa đơn': rows=self.invoice_rows
        elif self.f.view==self.cashview: rows=self.cash_rows
        elif self.f.view=='Chi tiết công nợ': rows=self.invoice_rows+self.other_rows
        else:
            summaries={}
            for original in self.invoice_rows+self.other_rows+self.cash_rows:
                r=deepcopy(original)
                k=(r.party,r.currency)
                s=summaries.setdefault(k,frappe._dict(party_type=r.party_type,party=r.party,party_name=r.party_name,currency=r.currency,
                                                    **{m:0.0 for m in self.measures()}))
                if original in self.cash_rows:
                    for field in [self.cashfield,'refunded']:s[field]+=flt(r.get(field))
                else:
                    fields=['invoiced','credit_note','allocated','adjustment','future_amount','remaining_balance','range0']+['range'+str(n) for n in self.ledger.range_numbers]
                    for field in fields:s[field]+=flt(r.get(field))
                    if r.voucher_type==self.invoice_type:s.outstanding+=r.outstanding
                    else:s.other_balance+=r.outstanding
                for field in ['remarks','sales_person','delivery_notes','future_ref','project','cost_center','party_account','customer_group','territory','customer_primary_contact','supplier_group','sales_partner']:
                    if r.get(field):
                        values=set((s.get(field) or '').split('\n'))-{''}
                        values.add(str(r[field]));s[field]='\n'.join(sorted(values))
            for s in summaries.values():
                s.advance=max(0,-s.other_balance)
                s.other_balance=max(0,s.other_balance)
                s.net_balance=s.outstanding+s.other_balance-s.advance
            rows=list(summaries.values())
        if self.f.ignore_accounts and self.is_detail(): rows=self.merge_vouchers(rows)
        if self.f.hide_reconciled_entries:
            rows=[r for r in rows if abs(flt(r.get('outstanding') if self.is_detail() else r.net_balance))>=10**-self.ledger.currency_precision or (self.f.for_revaluation_journals and abs(flt(r.get('outstanding_in_account_currency')))>=10**-self.ledger.currency_precision)]
        rows.sort(key=lambda r:(r.party,r.currency,str(r.get('posting_date') or ''),r.get('voucher_no') or '',str(r.get('due_date') or '')))
        return rows

    def merge_vouchers(self,rows):
        result={}
        for r in rows:
            k=(r.party,r.currency,r.voucher_type,r.voucher_no,r.get('payment_term'),r.get('due_date'))
            if k not in result: result[k]=deepcopy(r);result[k].party_account='';continue
            for field in set(self.measures()+['paid']):result[k][field]=flt(result[k].get(field))+flt(r.get(field))
        return list(result.values())

    def subtotals(self,rows):
        result=[];groups=defaultdict(list)
        for r in rows:groups[r.party,r.currency].append(r)
        for (party,currency),group in groups.items():
            result.extend(group)
            total=frappe._dict(party_type=self.f.party_type,party=party,party_name=_('Tổng')+' '+self.parties[party],currency=currency,bold=1)
            for field in self.measures():total[field]=sum(flt(r.get(field)) for r in group)
            result.append(total)
        return result

    def columns(self):
        cols=[dict(fieldname='party_type',label=_('Party Type'),fieldtype='Link',options='DocType',width=100),
              dict(fieldname='party',label=_('Party'),fieldtype='Dynamic Link',options='party_type',width=160),
              dict(fieldname='party_name',label=_('Tên đối tác'),fieldtype='Data',width=180)]
        detail=self.is_detail()
        if detail:
            cols += [dict(fieldname='posting_date',label=_('Posting Date'),fieldtype='Date',width=110),
                     dict(fieldname='voucher_type',label=_('Voucher Type'),fieldtype='Data',width=120),
                     dict(fieldname='voucher_no',label=_('Voucher No'),fieldtype='Dynamic Link',options='voucher_type',width=210)]
            if not self.f.ignore_accounts:cols.append(dict(fieldname='party_account',label=_('Tài khoản công nợ'),fieldtype='Link',options='Account',width=180))
            cols += [dict(fieldname='project',label='Project',fieldtype='Link',options='Project',width=130),
                     dict(fieldname='cost_center',label=_('Cost Center'),fieldtype='Link',options='Cost Center',width=130)]
        iscash=self.f.view==self.cashview
        if detail and not iscash:
            cols.append(dict(fieldname='due_date',label=_('Due Date'),fieldtype='Date',width=110))
            if self.payable:cols += [dict(fieldname='bill_no',label=_('Bill No'),fieldtype='Data',width=140),dict(fieldname='bill_date',label=_('Bill Date'),fieldtype='Date',width=110)]
            if self.f.based_on_payment_terms:
                cols.append(dict(fieldname='payment_term',label=_('Payment Term'),fieldtype='Data',width=160))
                cols.append(dict(fieldname='invoice_grand_total',label=_('Invoice Grand Total'),fieldtype='Currency',options='currency',width=160))
            if not self.payable:cols.append(dict(fieldname='po_no',label=_('Customer LPO'),fieldtype='Data',width=130))
        labels=[('invoiced','Giá trị hóa đơn'),('credit_note','Giảm trừ hóa đơn'),
                (self.cashfield,'Tiền đã trả NCC' if self.payable else 'Tiền khách đã trả'),
                ('refunded','Tiền NCC hoàn lại' if self.payable else 'Tiền hoàn khách'),
                ('allocated','Đã thanh toán/phân bổ vào hóa đơn'),('adjustment','Điều chỉnh công nợ hóa đơn'),
                ('advance','Ứng trước chưa phân bổ'),('outstanding','Hóa đơn còn phải trả' if self.payable else 'Hóa đơn còn phải thu'),
                ('other_balance','Công nợ khác'),('net_balance','Công nợ ròng')]
        if iscash: labels=[(self.cashfield,labels[2][1]),('refunded',labels[3][1]),('allocated_payment','Đã phân bổ công nợ'),('remaining_payment','Số dư chưa phân bổ')]
        elif detail: labels=[p for p in labels if p[0] in ['invoiced','credit_note','allocated','adjustment','outstanding','other_balance','advance']]
        def money(field,label):return dict(fieldname=field,label=_(label),fieldtype='Currency',options='currency',width=165)
        cols += [money(k,l) for k,l in labels]
        cols.append(dict(fieldname='age',label=_('Age (Days)'),fieldtype='Int',width=90)) if detail else None
        cols += [money('range0','Chưa đến hạn')]
        previous=0
        for n,bound in enumerate(self.ledger.ranges+['Above'],1):
            cols.append(money('range'+str(n),str(previous)+'–'+str(bound)))
            if str(bound).isdigit():previous=int(bound)+1
        if self.f.show_future_payments:
            cols += [money('future_amount','Future Payment Amount'),money('remaining_balance','Remaining Balance'),
                     dict(fieldname='future_ref',label=_('Future Payment Ref'),fieldtype='Data',width=180)]
        for flag,field,label in [('show_delivery_notes','delivery_notes','Delivery Notes'),('show_sales_person','sales_person','Sales Person'),('show_remarks','remarks','Remarks')]:
            if self.f.get(flag):cols.append(dict(fieldname=field,label=_(label),fieldtype='Data',width=220))
        for field,label,dt in ([('supplier_group','Supplier Group','Supplier Group')] if self.payable else [('customer_group','Customer Group','Customer Group'),('territory','Territory','Territory'),('customer_primary_contact','Customer Contact','Contact')]):
            cols.append(dict(fieldname=field,label=_(label),fieldtype='Link',options=dt,width=140))
        if self.f.sales_partner:cols.append(dict(fieldname='sales_partner',label=_('Sales Partner'),fieldtype='Data',width=140))
        cols.append(dict(fieldname='currency',label=_('Currency'),fieldtype='Link',options='Currency',width=80))
        return cols


def execute(filters=None, account_type='Receivable'):
    return PartyReport(filters,account_type).run()
