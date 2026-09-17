from llm.prompt_templates import InvoicePromptTemplate

def test_prompt_builder():
    prompt = InvoicePromptTemplate.build_extraction_prompt("Invoice #101 Total: $500")
    assert "Total Amount" in prompt
    assert "Invoice #101 Total: $500" in prompt
