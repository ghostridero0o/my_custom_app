# my_custom_app/api/account_resolver.py

import re
import frappe
from frappe.utils import cint

# -----------------------------
# Vietnamese normalize
# -----------------------------
_VN_MAP = str.maketrans({
    "á":"a","à":"a","ả":"a","ã":"a","ạ":"a",
    "ă":"a","ắ":"a","ằ":"a","ẳ":"a","ẵ":"a","ặ":"a",
    "â":"a","ấ":"a","ầ":"a","ẩ":"a","ẫ":"a","ậ":"a",
    "đ":"d",
    "é":"e","è":"e","ẻ":"e","ẽ":"e","ẹ":"e",
    "ê":"e","ế":"e","ề":"e","ể":"e","ễ":"e","ệ":"e",
    "í":"i","ì":"i","ỉ":"i","ĩ":"i","ị":"i",
    "ó":"o","ò":"o","ỏ":"o","õ":"o","ọ":"o",
    "ô":"o","ố":"o","ồ":"o","ổ":"o","ỗ":"o","ộ":"o",
    "ơ":"o","ớ":"o","ờ":"o","ở":"o","ỡ":"o","ợ":"o",
    "ú":"u","ù":"u","ủ":"u","ũ":"u","ụ":"u",
    "ư":"u","ứ":"u","ừ":"u","ử":"u","ữ":"u","ự":"u",
    "ý":"y","ỳ":"y","ỷ":"y","ỹ":"y","ỵ":"y",
})


def _norm(s: str) -> str:
    s = (s or "").lower().translate(_VN_MAP)
    return re.sub(r"\s+", " ", s).strip()


# -----------------------------
# Concept detection
# -----------------------------
def _pick_concept(q: str) -> str:
    q = _norm(q)

    if any(k in q for k in ["tien mat", "quy", "cash"]):
        return "cash"
    if any(k in q for k in ["ngan hang", "tien gui", "bank"]):
        return "bank"
    if any(k in q for k in ["phai thu", "receivable"]):
        return "receivable"
    if any(k in q for k in ["phai tra", "payable"]):
        return "payable"
    if any(k in q for k in ["ton kho", "hang ton"]):
        return "inventory"
    if any(k in q for k in ["tai san co dinh", "tscd"]):
        return "fixed_assets"
    if any(k in q for k in ["von chu"]):
        return "equity"
    if any(k in q for k in ["doanh thu", "thu nhap"]):
        return "revenue"
    if any(k in q for k in ["chi phi"]):
        return "expense"

    return "unknown"


def _concept_rules(concept: str):
    rules = {
        "cash": (["111"], ["tien mat", "quy"]),
        "bank": (["112"], ["ngan hang", "tien gui"]),
        "receivable": (["131"], ["phai thu"]),
        "payable": (["331"], ["phai tra"]),
        "inventory": (["152", "153", "154", "155", "156"], ["ton kho"]),
        "fixed_assets": (["211"], ["tai san co dinh"]),
        "equity": (["411", "421"], ["von chu"]),
        "revenue": (["511"], ["doanh thu"]),
        "expense": (["6", "8"], ["chi phi"]),
        "unknown": ([], []),
    }
    return rules.get(concept, ([], []))


# -----------------------------
# Score
# -----------------------------
def _score_account(row, prefixes, keywords, qn):
    name = row.get("name") or ""
    acc_no = (row.get("account_number") or "").strip()
    is_group = cint(row.get("is_group"))

    name_n = _norm(name)
    score = 0

    if is_group:
        score += 50

    for p in prefixes:
        if acc_no.startswith(p):
            score += 80
            if acc_no == p:
                score += 10

    for kw in keywords:
        if kw in name_n:
            score += 40

    if qn in name_n:
        score += 30

    return score


def _get_children(company, group_name, limit_children=50):
    try:
        lft, rgt = frappe.get_value("Account", group_name, ["lft", "rgt"])
        if lft and rgt:
            return frappe.get_all(
                "Account",
                filters={"company": company, "lft": [">", lft], "rgt": ["<", rgt]},
                fields=["name", "account_number", "is_group"],
                order_by="lft asc",
                limit_page_length=limit_children,
            )
    except Exception:
        pass

    return frappe.get_all(
        "Account",
        filters={"company": company, "parent_account": group_name},
        fields=["name", "account_number", "is_group"],
        limit_page_length=limit_children,
    )


# -----------------------------
# PUBLIC API
# -----------------------------
@frappe.whitelist()
def resolve_account_concept(company: str, query_text: str, limit: int = 10, include_children: bool = False, **kwargs):
    """
    Resolve Vietnamese finance concept → ERPNext Account group.
    Example: "tiền mặt", "công nợ nhà cung cấp", "tồn kho"
    """

    if not company:
        frappe.throw("company is required")

    text = (query_text or "").lower()

    KEYWORDS = {
        "tiền mặt": ["111"],
        "ngân hàng": ["112"],
        "phải thu": ["131"],
        "công nợ khách": ["131"],
        "phải trả": ["331"],
        "công nợ nhà cung cấp": ["331"],
        "tồn kho": ["152", "153", "155", "156"],
        "nguyên vật liệu": ["152"],
        "công cụ dụng cụ": ["153"],
        "thành phẩm": ["155"],
        "hàng hóa": ["156"],
        "tài sản cố định": ["211"],
        "chi phí trả trước": ["242"]
    }

    matched_prefix = None

    for k, prefixes in KEYWORDS.items():
        if k in text:
            matched_prefix = prefixes
            break

    if not matched_prefix:
        return {
            "matched": False,
            "accounts": []
        }

    accounts = frappe.get_all(
        "Account",
        filters={
            "company": company,
            "account_number": ["in", matched_prefix]
        },
        fields=["name", "account_number", "is_group"],
        limit_page_length=limit
    )

    if cint(include_children):
        expanded = []
        seen = set()
        for acc in accounts:
            name = acc.get("name")
            if not name or name in seen:
                continue
            seen.add(name)
            expanded.append(acc)
            if cint(acc.get("is_group")):
                for child in _get_children(company, name, limit_children=limit):
                    cname = child.get("name")
                    if cname and cname not in seen:
                        seen.add(cname)
                        expanded.append(child)
        accounts = expanded

    return {
        "matched": True,
        "accounts": accounts
    }
