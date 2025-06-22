from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
import uvicorn
import json

app = FastAPI()

@app.post("/webhook")
async def webhook(request: Request):
    try:
        form_data = await request.form()  # URL 인코딩된 데이터 수신
        data = json.loads(form_data['payload'])  # JSON 문자열을 파싱
        print(data)  # 수신된 데이터 출력
        return {"status": "success"}
    except Exception as e:
        print(f"Error: {e}")  # 오류 메시지 출력
        return {"status": "error", "message": str(e)}

@app.get("/", response_class=HTMLResponse)
async def read_root():
    return """
    <html>
        <head>
            <title>Webhook Test</title>
        </head>
        <body>
            <h1>Webhook Test</h1>
            <form action="/webhook" method="post">
                <textarea name="payload" rows="10" cols="50" placeholder='{"key": "value"}'></textarea><br>
                <button type="submit">Send Webhook</button>
            </form>
        </body>
    </html>
    """

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=23105)
