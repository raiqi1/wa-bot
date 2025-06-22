import os
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import JSONResponse
from langchain_community.document_loaders import PyPDFLoader
from langchain.text_splitter import CharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_openai import ChatOpenAI
from langchain.chains.question_answering import load_qa_chain
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()
UPLOAD_DIR = "uploads"
VECTOR_DIR = "vectorstore/db_faiss"
os.makedirs(UPLOAD_DIR, exist_ok=True)

embeddings = HuggingFaceEmbeddings(
    model_name="sentence-transformers/all-MiniLM-L6-v2",
    model_kwargs={'device': 'cpu'}
)

llm = ChatOpenAI(
    model=os.getenv("MODEL"),
    api_key=os.getenv("OPENROUTER_API_KEY"),
    base_url=os.getenv("OPENROUTER_BASE_URL"),
    temperature=0.7
)

vectorstore = None


@app.post("/upload-pdf")
async def upload_pdf(file: UploadFile = File(...)):
    try:
        filepath = os.path.join(UPLOAD_DIR, file.filename)
        with open(filepath, "wb") as f:
            f.write(await file.read())

        loader = PyPDFLoader(filepath)
        documents = loader.load()

        splitter = CharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
        docs = splitter.split_documents(documents)

        global vectorstore
        vectorstore = FAISS.from_documents(docs, embeddings)
        vectorstore.save_local(VECTOR_DIR)

        return {
            "message": "PDF uploaded and vector DB created",
            "chunks": len(docs),
            "filename": file.filename
        }

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.post("/ask")
async def ask_question(question: str = Form(...)):
    try:
        global vectorstore
        
        if not vectorstore:
            if not os.path.exists(VECTOR_DIR):
                return JSONResponse(
                    status_code=400,
                    content={"error": "No PDF uploaded yet. Please upload a PDF first."}
                )
            vectorstore = FAISS.load_local(
                VECTOR_DIR,
                embeddings,
                allow_dangerous_deserialization=True
            )

        relevant_docs = vectorstore.similarity_search(question, k=3)
        
        if not relevant_docs:
            return JSONResponse(
                status_code=400,
                content={"error": "No relevant documents found."}
            )

        chain = load_qa_chain(llm, chain_type="stuff")
        result = chain.run(input_documents=relevant_docs, question=question)
        
        answer = str(result)
        
        return {
            "question": question,
            "answer": answer,
            "source": "📄 Based on uploaded PDF",
            "found_chunks": len(relevant_docs)
        }

    except Exception as e:
        print(f"Error: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.post("/ask-direct")
async def ask_direct(question: str = Form(...)):
    """Direct LLM query without PDF context"""
    try:
        result = llm.invoke(question)
        if hasattr(result, 'content'):
            answer = result.content
        else:
            answer = str(result)
            
        return {
            "question": question,
            "answer": answer,
            "source": "🤖 Direct LLM"
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/status")
async def get_status():
    global vectorstore
    status = {
        "vectorstore_loaded": vectorstore is not None,
        "vectorstore_dir_exists": os.path.exists(VECTOR_DIR),
        "model": os.getenv("MODEL"),
    }
    
    if vectorstore:
        try:
            test_docs = vectorstore.similarity_search("test", k=1)
            status["has_documents"] = len(test_docs) > 0
        except:
            status["has_documents"] = False
    
    return status


@app.delete("/clear")
async def clear_vectorstore():
    global vectorstore
    try:
        vectorstore = None
        
        if os.path.exists(VECTOR_DIR):
            import shutil
            shutil.rmtree(VECTOR_DIR)
        
        if os.path.exists(UPLOAD_DIR):
            for file in os.listdir(UPLOAD_DIR):
                os.remove(os.path.join(UPLOAD_DIR, file))
        
        return {"message": "Vectorstore and uploaded files cleared"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})