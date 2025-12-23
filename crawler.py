import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime
import time
import re
import os

# --- 환경 설정 ---
SLACK_WEBHOOK_URL = os.environ.get('SLACK_WEBHOOK_URL')
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'ko-KR,ko;q=0.8,en-US;q=0.5,en;q=0.3',
}

def fetch_detail_content(url):
    """상세 페이지 본문 추출 (사람인 우회 및 노이즈 제거 강화)"""
    try:
        time.sleep(2)
        target_url = url
        
        # [수정] 사람인의 경우 iframe 본문 주소로 강제 전환하여 '로그인' 메시지 회피
        if "saramin.co.kr" in url and "rec_idx=" in url:
            rec_idx_match = re.search(r'rec_idx=(\d+)', url)
            if rec_idx_match:
                target_url = f"https://www.saramin.co.kr/zf_user/jobs/relay/view-detail?rec_idx={rec_idx_match.group(1)}"

        res = requests.get(target_url, headers=HEADERS, timeout=15)
        res.encoding = 'utf-8'
        soup = BeautifulSoup(res.text, 'html.parser')

        # 불필요한 요소 제거
        for tag in soup(["script", "style", "nav", "footer", "header", "button", "aside", "iframe"]):
            tag.decompose()

        # 본문 핵심 선택자 리스트
        selectors = [
            '.user_content', '.recruit_view_cont', '.view_con', 
            '.job_detail', '.template_area', '.cont_jview', '.wrap_jv_cont'
        ]
        
        content_text = ""
        for sel in selectors:
            target = soup.select_one(sel)
            if target:
                content_text = target.get_text(separator="\n", strip=True)
                break
        
        # 선택자로 못 찾은 경우 전체 텍스트 추출 시도
        if not content_text or len(content_text) < 100:
            content_text = soup.get_text(separator="\n", strip=True)

        # [수정] 노이즈 필터링 (로그인 관련 텍스트가 본문의 주가 되면 무효 처리)
        noise_keywords = ["로그인", "회원가입", "아이디 찾기", "비밀번호 찾기", "모바일네트워크"]
        if any(k in content_text[:200] for k in noise_keywords) and len(content_text) < 500:
            return "본문 내용 확인 불가 (상세 페이지 링크 참조)"

        return content_text[:15000] # 저장 용량 제한
    except Exception as e:
        return f"수집 실패: {str(e)}"

def get_bep_jobs():
    """BEP 수집 로직 - 전체 목록 기반 키워드 필터링 (누락 방지)"""
    url = "https://bep.co.kr/Career/recruitment"
    jobs = []
    try:
        response = requests.get(url, headers=HEADERS)
        response.encoding = 'utf-8'
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 모든 공고 링크(recruitmentView?idx=) 탐색
        links = soup.find_all('a', href=re.compile(r'recruitmentView\?idx='))
        for l in links:
            text = l.get_text(" ", strip=True)
            # 상태값(모집중)과 키워드(전기차/충전/운영/워터) 동시 확인
            if "모집중" in text and any(k in text for k in ["전기차", "충전", "워터", "WATER", "운영", "매니저"]):
                href = l.get('href', '')
                full_link = f"https://bep.co.kr{href}" if not href.startswith('http') else href
                title = text.replace("모집중", "").strip()
                jobs.append(['BEP', title, "공고 참조", full_link])
    except Exception as e:
        print(f"BEP 크롤링 실패: {e}")
    return jobs

def get_saramin_jobs(companies):
    """사람인 특정 기업 수집"""
    base_url = "https://www.saramin.co.kr/zf_user/search/recruit"
    jobs = []
    for company in companies:
        try:
            params = {'searchword': company, 'searchType': 'search'}
            res = requests.get(base_url, headers=HEADERS, params=params)
            soup = BeautifulSoup(res.text, 'html.parser')
            items = soup.select('.item_recruit')
            for item in items:
                co_tag = item.select_one('.corp_name a')
                if not co_tag: continue
                co_name = co_tag.text.strip()
                if company in co_name.replace("(주)", "").replace("주식회사", ""):
                    title_tag = item.select_one('.job_tit a')
                    link = "https://www.saramin.co.kr" + title_tag['href']
                    jobs.append([co_name, title_tag.text.strip(), "공고 참조", link])
            time.sleep(1.5)
        except: continue
    return jobs

def send_slack_message(new_jobs):
    if not SLACK_WEBHOOK_URL or not new_jobs: return
    message = f"📢 *신규 전기차 충전 채용 공고 ({len(new_jobs)}건)*\n\n"
    for job in new_jobs:
        message += f"• *[{job[0]}]* {job[1]}\n  <{job[3]}|공고 보기>\n\n"
    requests.post(SLACK_WEBHOOK_URL, json={"text": message})

def main():
    target_companies = ["대영채비", "이브이시스", "플러그링크", "볼트업", "차지비", "에버온"]
    today = datetime.now().strftime('%Y-%m-%d')
    
    # 파일 경로 설정
    master_file = "job_listings_all.csv"
    comp_file = "Recruitment_completed.csv"
    ency_file = "encyclopedia.csv"

    # 기존 데이터 로드
    df_master = pd.read_csv(master_file) if os.path.exists(master_file) else pd.DataFrame(columns=['company', 'title', 'experience', 'link', 'first_seen'])
    df_ency = pd.read_csv(ency_file) if os.path.exists(ency_file) else pd.DataFrame(columns=['link', 'company', 'title', 'content', 'last_updated'])
    df_comp = pd.read_csv(comp_file) if os.path.exists(comp_file) else pd.DataFrame(columns=['company', 'title', 'experience', 'link', 'completed_date'])

    # 1. 크롤링 수행
    print("데이터 수집 시작...")
    bep_data = get_bep_jobs()
    saram_data = get_saramin_jobs(target_companies)
    current_jobs = bep_data + saram_data
    df_current = pd.DataFrame(current_jobs, columns=['company', 'title', 'experience', 'link'])

    # [중요] 안전장치: 수집에 성공한 회사 리스트 추출
    successful_scan_companies = df_current['company'].unique()

    # 2. 신규 공고 처리 (Master 업데이트)
    new_entries = df_current[~df_current['link'].isin(df_master['link'])].copy()
    if not new_entries.empty:
        new_entries['first_seen'] = today
        send_slack_message(new_entries.values.tolist())
        df_master = pd.concat([df_master, new_entries], ignore_index=True)

    # 3. 채용 종료 처리 (정교한 로직 적용)
    # 로직: 마스터에는 있으나 오늘 크롤링 결과에는 없는 공고
    is_missing = ~df_master['link'].isin(df_current['link'])
    # 하지만 해당 회사 자체가 오늘 크롤링에서 단 한 건도 발견되지 않았다면 '수집 실패'로 간주하고 보류
    is_safe_to_close = df_master['company'].isin(successful_scan_companies)
    
    closed_entries = df_master[is_missing & is_safe_to_close].copy()
    
    if not closed_entries.empty:
        closed_entries['completed_date'] = today
        df_comp = pd.concat([df_comp, closed_entries], ignore_index=True)
        # 마스터에서 실제로 제거
        df_master = df_master[~(is_missing & is_safe_to_close)]
        print(f"{len(closed_entries)}건의 채용 종료가 기록되었습니다.")

    # 4. 백과사전(Encyclopedia) 및 본문 업데이트
    # 대상: 백과사전에 아예 없거나, 기존 내용이 '실패' 혹은 '로그인' 관련인 경우
    failed_keywords = ["본문 내용을 찾을 수 없습니다", "로그인", "수집 실패", "확인 불가"]
    is_failed_content = df_ency['content'].apply(lambda x: any(k in str(x) for k in failed_keywords))
    
    # 4-1. 기존 백과사전에서 실패한 링크들 추출
    links_to_retry = df_ency[is_failed_content]['link'].tolist()
    # 4-2. 오늘 크롤링 된 것 중 백과사전에 아예 없는 링크들
    links_to_add = df_current[~df_current['link'].isin(df_ency['link'])]['link'].tolist()
    
    target_links = list(set(links_to_retry + links_to_add))
    
    if target_links:
        print(f"상세 내용 {len(target_links)}건 수집/갱신 중...")
        for link in target_links:
            # df_current 혹은 df_master에서 정보 추출
            source_row = df_current[df_current['link'] == link]
            if source_row.empty: source_row = df_master[df_master['link'] == link]
            if source_row.empty: continue
            
            row = source_row.iloc[0]
            content = fetch_detail_content(link)
            
            if link in df_ency['link'].values:
                df_ency.loc[df_ency['link'] == link, ['content', 'last_updated']] = [content, today]
            else:
                new_row = pd.DataFrame([{'link': link, 'company': row['company'], 'title': row['title'], 'content': content, 'last_updated': today}])
                df_ency = pd.concat([df_ency, new_row], ignore_index=True)

    # 5. 파일 저장 (최종)
    df_master.to_csv(master_file, index=False, encoding='utf-8-sig')
    df_comp.to_csv(comp_file, index=False, encoding='utf-8-sig')
    df_ency.to_csv(ency_file, index=False, encoding='utf-8-sig')
    print(f"[{today}] 모든 작업이 성공적으로 완료되었습니다.")

if __name__ == "__main__":
    main()
