import os
import pandas as pd
from slack_sdk import WebClient
from datetime import datetime

SLACK_TOKEN = os.environ.get("SLACK_BOT_TOKEN")
CANVAS_ID = os.environ.get("SLACK_CANVAS_ID")
CSV_PATH = "job_listings_all.csv"

def update_slack_canvas():
    if not SLACK_TOKEN or not CANVAS_ID:
        return

    client = WebClient(token=SLACK_TOKEN)

    try:
        if not os.path.exists(CSV_PATH):
            return
            
        df = pd.read_csv(CSV_PATH)
        df = df.sort_values(by='first_seen', ascending=False)
        today = datetime.now().strftime('%Y-%m-%d')
        
        markdown_text = f"# 🚀 채용 정보 리스트 ({today})\n\n"
        
        # --- [표 너비 최적화 트릭 적용] ---
        # 1. '공고 제목' 헤더 뒤에 전각 공백(　)이나 많은 띄어쓰기를 넣어 열 너비를 강제로 확보합니다.
        # 2. 링크는 헤더 이름을 '🔗'로 줄여서 열 전체를 좁게 만듭니다.
        
        markdown_text += "| 회사명 | 공고 제목" + " " * 30 + " | 경력 | 등록일 | 🔗 |\n"
        markdown_text += "|:---|:---|:---|:---|:---:|\n"
        
        for _, row in df.head(40).iterrows(): # 데이터 노출 개수를 40개로 상향
            # 제목을 좀 더 길게 노출 (가로 너비 확보용)
            title = row['title']
            if len(title) > 45:
                title = title[:45] + ".."
            
            # 링크 열은 오직 아이콘 하나만 (너비 최소화)
            link_icon = f"[🔗]({row['link']})"
            
            markdown_text += (
                f"| {row['company']} "
                f"| {title} "
                f"| {row['experience']} "
                f"| {row['first_seen']} "
                f"| {link_icon} |\n"
            )
            
        markdown_text += f"\n\n---\n*마지막 업데이트: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*"

        response = client.canvases_edit(
            canvas_id=CANVAS_ID,
            changes=[{
                "operation": "replace",
                "document_content": {
                    "type": "markdown",
                    "markdown": markdown_text
                }
            }]
        )
        
        if response["ok"]:
            print("✅ 최적화된 표 형식으로 업데이트 성공!")

    except Exception as e:
        print(f"❌ 오류: {e}")

if __name__ == "__main__":
    update_slack_canvas()
