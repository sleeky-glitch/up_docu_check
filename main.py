import streamlit as st
from openai import OpenAI
import PyPDF2
import docx

def extract_text_from_pdf(pdf_file):
    pdf_reader = PyPDF2.PdfReader(pdf_file)
    text = ""
    for page in pdf_reader.pages:
        text += page.extract_text()
    return text

def extract_text_from_docx(docx_file):
    doc = docx.Document(docx_file)
    text = ""
    for paragraph in doc.paragraphs:
        text += paragraph.text + "\n"
    return text

def extract_text_from_txt(txt_file):
    return str(txt_file.read(), "utf-8")

def get_document_text(uploaded_file):
    if uploaded_file.type == "application/pdf":
        return extract_text_from_pdf(uploaded_file)
    elif uploaded_file.type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        return extract_text_from_docx(uploaded_file)
    elif uploaded_file.type == "text/plain":
        return extract_text_from_txt(uploaded_file)
    else:
        st.error("Unsupported file type. Please upload PDF, DOCX, or TXT files.")
        return None

def analyze_document_approval(client, circular_text, proposal_text):
    prompt = f"""
    You are an expert reviewer. Document 1 is an official circular (policy/guideline/communication). Document 2 is a proposal that claims to be based on Document 1.

    Your task:
    1. Carefully read both documents.
    2. Decide if the proposal (Document 2) can be approved strictly on the basis of the circular (Document 1).
    3. If it can be approved, state "APPROVED" and briefly explain why.
    4. If it cannot be approved, state "REJECTED" and clearly list the reasons for rejection, referencing specific requirements or gaps.

    Document 1 (Circular):
    {circular_text[:3000]}

    Document 2 (Proposal):
    {proposal_text[:3000]}

    Please provide your answer in this format:
    Decision: APPROVED/REJECTED

    Explanation:
    (Your detailed reasoning here)

    Key Points Analysis:
    - Compliance with circular requirements
    - Missing elements (if any)
    - Alignment with stated policies
    - Recommendations for improvement (if rejected)
    """
    try:
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are an expert reviewer for proposals and circulars, specializing in compliance analysis and approval decisions."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=1000,
            temperature=0.2
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Error analyzing documents: {str(e)}"

def main():
    st.set_page_config(
        page_title="Proposal Approval Analyzer",
        page_icon="✅",
        layout="wide"
    )
    st.title("✅ Proposal Approval Analyzer")
    st.markdown("Upload a circular and a proposal to determine if the proposal can be approved based on the circular requirements.")

    # Get API key from Streamlit secrets (user never sees this)
    if "openai" not in st.secrets or "api_key" not in st.secrets["openai"]:
        st.error("AI API key not found in app configuration. Please contact the administrator.")
        st.stop()
    api_key = st.secrets["openai"]["api_key"]

    try:
        client = OpenAI(api_key=api_key)
    except Exception as e:
        st.error("Error initializing AI backend. Please contact the administrator.")
        return

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("📋 Circular (Document 1)")
        st.caption("Upload the official circular, policy, or guideline document")
        doc1_file = st.file_uploader(
            "Upload circular document",
            type=['pdf', 'docx', 'txt'],
            key="doc1"
        )
        if doc1_file:
            st.success(f"✅ {doc1_file.name} uploaded")
    
    with col2:
        st.subheader("📄 Proposal (Document 2)")
        st.caption("Upload the proposal document to be reviewed")
        doc2_file = st.file_uploader(
            "Upload proposal document",
            type=['pdf', 'docx', 'txt'],
            key="doc2"
        )
        if doc2_file:
            st.success(f"✅ {doc2_file.name} uploaded")

    if doc1_file and doc2_file:
        if st.button("🔍 Analyze Proposal for Approval", type="primary"):
            with st.spinner("Extracting text from documents..."):
                circular_text = get_document_text(doc1_file)
                proposal_text = get_document_text(doc2_file)
                
                if circular_text and proposal_text:
                    st.success("Text extraction completed!")
                    
                    with st.expander("📖 Document Previews"):
                        col1, col2 = st.columns(2)
                        with col1:
                            st.subheader("Circular Preview")
                            st.text_area("", circular_text[:500] + "...", height=200, disabled=True)
                        with col2:
                            st.subheader("Proposal Preview")
                            st.text_area("", proposal_text[:500] + "...", height=200, disabled=True)
                    
                    with st.spinner("Analyzing proposal against circular requirements..."):
                        analysis_result = analyze_document_approval(client, circular_text, proposal_text)
                        
                        st.subheader("🎯 Approval Decision")
                        
                        # Check if approved or rejected and display accordingly
                        if "APPROVED" in analysis_result.upper():
                            st.success("✅ PROPOSAL APPROVED")
                        elif "REJECTED" in analysis_result.upper():
                            st.error("❌ PROPOSAL REJECTED")
                        
                        st.markdown(analysis_result)
                        
                        st.subheader("📊 Document Statistics")
                        col1, col2, col3, col4 = st.columns(4)
                        with col1:
                            st.metric("Circular Length", f"{len(circular_text.split())} words")
                        with col2:
                            st.metric("Proposal Length", f"{len(proposal_text.split())} words")
                        with col3:
                            st.metric("Circular Characters", f"{len(circular_text):,}")
                        with col4:
                            st.metric("Proposal Characters", f"{len(proposal_text):,}")
                else:
                    st.error("Failed to extract text from one or both documents.")

    with st.expander("ℹ️ How to use"):
        st.markdown("""
        1. **Upload the circular** (Document 1) - This should be the official policy, guideline, or circular document
        2. **Upload the proposal** (Document 2) - This should be the proposal that needs to be reviewed for approval
        3. **Click Analyze** to get an AI-powered approval decision
        4. **Review the results** to see if the proposal is approved or rejected, along with detailed reasoning
        
        **The system will:**
        - Compare the proposal against circular requirements
        - Identify compliance gaps or missing elements
        - Provide clear approval/rejection decision
        - Offer recommendations for improvement if rejected
        """)

    st.markdown("---")
    st.markdown("Built by SLEEKY @ BSPL AI Team | Proposal Approval Analyzer")

if __name__ == "__main__":
    main()
