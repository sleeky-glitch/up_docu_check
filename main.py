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

def analyze_document_correlation(client, doc1_text, doc2_text):
    prompt = f"""
    Please analyze the correlation between these two documents and provide a detailed comparison:

    Document 1:
    {doc1_text[:3000]}

    Document 2:
    {doc2_text[:3000]}

    Please provide:
    1. Overall correlation score (0-100%)
    2. Key similarities
    3. Key differences
    4. Common themes or topics
    5. Writing style comparison
    6. Content overlap analysis
    7. Recommendations or insights

    Format your response in a clear, structured manner.
    """
    try:
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are an expert document analyst specializing in comparing and correlating textual content."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=1500,
            temperature=0.3
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Error analyzing documents: {str(e)}"

def main():
    st.set_page_config(
        page_title="Document Correlation Analyzer",
        page_icon="📄",
        layout="wide"
    )
    st.title("📄 Document Correlation Analyzer")
    st.markdown("Upload two documents to analyze their correlation and similarities using advanced AI.")

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
        st.subheader("📄 Document 1")
        doc1_file = st.file_uploader(
            "Upload first document",
            type=['pdf', 'docx', 'txt'],
            key="doc1"
        )
        if doc1_file:
            st.success(f"✅ {doc1_file.name} uploaded")
    with col2:
        st.subheader("📄 Document 2")
        doc2_file = st.file_uploader(
            "Upload second document",
            type=['pdf', 'docx', 'txt'],
            key="doc2"
        )
        if doc2_file:
            st.success(f"✅ {doc2_file.name} uploaded")

    if doc1_file and doc2_file:
        if st.button("🔍 Analyze Document Correlation", type="primary"):
            with st.spinner("Extracting text from documents..."):
                doc1_text = get_document_text(doc1_file)
                doc2_text = get_document_text(doc2_file)
                if doc1_text and doc2_text:
                    st.success("Text extraction completed!")
                    with st.expander("📖 Document Previews"):
                        col1, col2 = st.columns(2)
                        with col1:
                            st.subheader("Document 1 Preview")
                            st.text_area("", doc1_text[:500] + "...", height=200, disabled=True)
                        with col2:
                            st.subheader("Document 2 Preview")
                            st.text_area("", doc2_text[:500] + "...", height=200, disabled=True)
                    with st.spinner("Analyzing document correlation..."):
                        analysis_result = analyze_document_correlation(client, doc1_text, doc2_text)
                        st.subheader("🎯 Correlation Analysis Results")
                        st.markdown(analysis_result)
                        st.subheader("📊 Document Statistics")
                        col1, col2, col3, col4 = st.columns(4)
                        with col1:
                            st.metric("Doc 1 Length", f"{len(doc1_text.split())} words")
                        with col2:
                            st.metric("Doc 2 Length", f"{len(doc2_text.split())} words")
                        with col3:
                            st.metric("Doc 1 Characters", f"{len(doc1_text):,}")
                        with col4:
                            st.metric("Doc 2 Characters", f"{len(doc2_text):,}")
                else:
                    st.error("Failed to extract text from one or both documents.")

    with st.expander("ℹ️ How to use"):
        st.markdown("""
        1. **Upload two documents** (PDF, DOCX, or TXT format)
        2. **Click Analyze** to get a detailed correlation analysis powered by advanced AI
        3. **Review the results** including correlation scores, similarities, differences, and insights
        """)

    st.markdown("---")
    st.markdown("Built by SLEEKY @ BSPL AI Team | Document Correlation Analyzer")

if __name__ == "__main__":
    main()
