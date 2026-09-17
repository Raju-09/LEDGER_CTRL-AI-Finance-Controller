class InvoicePromptTemplate:
    @staticmethod
    def build_extraction_prompt(raw_ocr_text: str) -> str:
        return f"""Extract the following fields from the invoice text:
- Merchant Name
- Total Amount
- Currency
- Date (ISO format)
- Line Items

Text:
{raw_ocr_text}"""
