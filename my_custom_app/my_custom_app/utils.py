import frappe

@frappe.whitelist()
def number_to_words_vietnamese(number):
    """
    Chuyển đổi số thành chữ tiếng Việt và thêm từ 'chẵn' nếu số là nguyên.
    """
    # Kiểm tra và làm tròn số nếu là số thực
    if not isinstance(number, (int, float)):
        return "Số không hợp lệ!"
    number = round(number)  # Làm tròn số thực và giữ phần nguyên

    # Các số cơ bản
    words = {
        0: "không",
        1: "một",
        2: "hai",
        3: "ba",
        4: "bốn",
        5: "năm",
        6: "sáu",
        7: "bảy",
        8: "tám",
        9: "chín",
    }

    def convert_three_digits(num):
        """Chuyển đổi số có 3 chữ số thành chữ với quy tắc 'x0x' đọc là 'x trăm linh x'."""
        hundred = num // 100
        ten = (num % 100) // 10
        unit = num % 10

        result = []
        if hundred:
            result.append(f"{words[hundred]} trăm")
        if ten:
            if ten == 1:
                result.append("mười")
            elif ten == 0:  # Xử lý trường hợp "x0x"
                if unit != 0:
                    result.append("linh")
            else:
                result.append(f"{words[ten]} mươi")
        if unit:
            if unit == 1 and ten != 0:
                result.append("mốt")
            elif unit == 5 and ten != 0:
                result.append("lăm")
            else:
                result.append(words[unit])

        return " ".join(result)

    # Chuyển đổi phần nguyên
    def convert_integer(num):
        result = []
        unit_names = ["", "nghìn", "triệu", "tỷ"]
        group = 0
        while num > 0:
            part = num % 1000
            if part > 0:
                result.insert(0, f"{convert_three_digits(part)} {unit_names[group]}".strip())
            num //= 1000
            group += 1
        return " ".join(result)

    # Chuyển đổi số nguyên đã làm tròn
    integer_words = convert_integer(number)

    # Thêm từ "đồng" và "chẵn"
    return f"{integer_words.capitalize()} đồng chẵn./"
    pass