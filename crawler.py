import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime
import time
import re
import os

# --- 슬랙 설정 (GitHub Secrets에서 관리 권장) ---
SLACK_WEBHOOK_URL = os.environ.get('SLACK_WEBHOOK_URL')

def get_bep_jobs():
    url = "https://bep.co.kr/Career/recruitment?type=3"
    headers = {'User-Agent': 'Mozilla/5.0'}
    jobs = []
    try:
        response = requests.get(url, headers=headers)
        response.encoding = 'utf-8'
        soup = BeautifulSoup(response.text, 'html.parser')
        all_links = soup.find_all('a', href=re.compile(r'recruitmentView\?idx='))
        for link_tag in all_links:
            text = link_tag.get_text(" ", strip=True)
            if "모집중" not in text: continue
            if not any(k in text for k in ["전기차", "충전", "워터", "WATER"]): continue
            href = link_tag.get('href', '')
            full_link = f"https://bep.co.kr{href}" if not href.startswith('http') else href
            title = text.replace("모집중", "").replace("전기차충전사업부문", "").strip()
            exp = "공고 확인"
            match = re.search(r'\(([^)]*(?:경력|신입|무관)[^)]*)\)', title)
            if match:
                exp = match.group(1)
                title = title.replace(match.group(0), "").strip()
            jobs.append(['BEP', title, exp, full_link])
    except Exception as e:
        print(f"BEP 크롤링 오류: {e}")
    return jobs

def get_saramin_jobs(companies):
    base_url = "https://www.saramin.co.kr/zf_user/search/recruit"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    jobs = []
    for company in companies:
        params = {'searchword': company, 'searchType': 'search'}
        try:
            response = requests.get(base_url, headers=headers, params=params)
            soup = BeautifulSoup(response.text, 'html.parser')
            items = soup.select('.item_recruit')
            for item in items:
                co_tag = item.select_one('.corp_name a')
                if not co_tag: continue
                co_name = co_tag.text.strip()
                if company in co_name.replace("(주)", "").replace("주식회사", ""):
                    title_tag = item.select_one('.job_tit a')
                    title = title_tag.text.strip()
                    link = "https://www.saramin.co.kr" + title_tag['href']
                    conds = item.select('.job_condition span')
                    exp = conds[1].text.strip() if len(conds) > 1 else "정보 없음"
                    jobs.append([co_name, title, exp, link])
            time.sleep(1)
        except Exception as e:
            print(f"사람인 {company} 오류: {e}")
    return jobs

def send_slack_message(new_jobs):
    if not SLACK_WEBHOOK_URL or not new_jobs:
        return
    
    count = len(new_jobs)
    message = f"📢 *신규 전기차 충전 채용 공고 ({count}건)*\n\n"
    for job in new_jobs:
        message += f"• *[{job[0]}]* {job[1]} ({job[2]})\n  <{job[3]}|공고 보기>\n\n"
    
    payload = {"text": message}
    requests.post(SLACK_WEBHOOK_URL, json=payload)

def main():
    saramin_target = ["대영채비", "이브이시스", "플러그링크", "볼트업", "차지비", "에버온"]
    today_str = datetime.now().strftime('%Y-%m-%d')
    
    # 1. 크롤링 수행
    print(f"[{today_str}] 데이터 수집 시작...")
    current_data = get_bep_jobs() + get_saramin_jobs(saramin_target)
    df_current = pd.DataFrame(current_data, columns=['company', 'title', 'experience', 'link'])
    
    # 2. 전날(기존) 데이터 로드 및 비교
    master_file = "job_listings_all.csv"
    new_jobs_list = []
    
    if os.path.exists(master_file):
        df_old = pd.read_csv(master_file)
        # 링크(link)를 기준으로 기존에 없던 공고만 추출
        df_new = df_current[~df_current['link'].isin(df_old['link'])]
        new_jobs_list = df_new.values.tolist()
        
        # 신규 데이터가 있다면 마스터 파일 업데이트
        if not df_new.empty:
            df_updated = pd.concat([df_old, df_new], ignore_index=True)
            df_updated.to_csv(master_file, index=False, encoding='utf-8-sig')
            # 신규 파일 별도 저장
            df_new.to_csv(f"new_jobs_{today_str}.csv", index=False, encoding='utf-8-sig')
    else:
        # 최초 실행 시 현재 데이터를 마스터로 저장
        df_current.to_csv(master_file, index=False, encoding='utf-8-sig')
        new_jobs_list = current_data
        
    # 3. 슬랙 알림 발송
    if new_jobs_list:
        print(f"신규 공고 {len(new_jobs_list)}건 발견! 슬랙 전송 중...")
        send_slack_message(new_jobs_list)
    else:
        print("신규 공고가 없습니다.")

if __name__ == "__main__":
    main()
