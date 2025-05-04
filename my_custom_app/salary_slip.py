import frappe
from my_custom_app.utils import number_to_words_vietnamese

def before_save(doc, method):
    # G?i hàm chuy?n d?i s? thành ch?
    if doc.rounded_total:
        doc.total_in_words = number_to_words_vietnamese(doc.rounded_total)
