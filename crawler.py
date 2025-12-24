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
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
    'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7'
}

def fetch_detail_content(url):
    """상세 본문 추출: 텍스트 우선, 부족하면 이미지 URL 수집"""
    try:
        time.sleep(1.5)
        target_url = url
        if "saramin.co.kr" in url and "rec_idx=" in url:
            rec_idx_match = re.search(r'rec_idx=(\d+)', url)
            if rec_idx_match:
                target_url = f"https://www.saramin.co.kr/zf_user/jobs/relay/view-detail?rec_idx={rec_idx_match.group(1)}"

        res = requests.get(target_url, headers=HEADERS, timeout=15)
        res.encoding = 'utf-8'
        soup = BeautifulSoup(res.text, 'html.parser')

        for tag in soup(["script", "style", "nav", "footer", "header", "button", "aside"]):
            tag.decompose()

        selectors = ['.user_content', '.recruit_view_cont', '.view_con', '.job_detail', '.template_area', '.section_view']
        content_area = None
        for sel in selectors:
            content_area = soup.select_one(sel)
            if content_area: break
        
        if not content_area: content_area = soup.body

        text_content = content_area.get_text(separator="\n", strip=True) if content_area else ""
        
        poor_keywords = ["채용공고 상세", "본문 내용을 찾을 수 없습니다", "로그인"]
        is_poor = len(text_content) < 150 or any(text_content.strip() == k for k in poor_keywords)

        if is_poor and content_area:
            imgs = content_area.find_all('img')
            img_urls = [ (img.get('src') or img.get('data-src')) for img in imgs ]
            clean_imgs = [ "https:" + i if i.startswith('//') else i for i in img_urls if i and not any(x in i.lower() for x in ["icon", "logo", "common"])]
            if clean_imgs:
                return "[이미지 공고] " + ", ".join(clean_imgs)

        return text_content[:20000] if len(text_content) > 50 else "상세 내용은 링크를 참조해 주세요."
    except Exception as e:
        return f"수집 실패: {str(e)}"

def get_bep_jobs():
    """BEP(워터) 전기차충전사업부문 수집 보완"""
    url = "https://bep.co.kr/Career/recruitment?type=3"
    jobs = []
    try:
        # 세션을 사용하여 쿠키 등 유지
        with requests.Session() as s:
            response = s.get(url, headers=HEADERS, timeout=15)
            response.encoding = 'utf-8'
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # BEP 사이트의 공고 리스트는 보통 'board_list' 또는 'table' 구조 내의 a 태그에 존재
            # 상세 페이지 링크 패턴: /Career/recruitmentView?idx=...
            links = soup.find_all('a', href=re.compile(r'recruitmentView\?idx='))
            
            for l in links:
                # 제목 추출 (내부 span이나 strong 태그가 있을 수 있음)
                title_text = l.get_text(" ", strip=True)
                if not title_text or "목록" in title_text or "이전글" in title_text or "다음글" in title_text:
                    continue
                
                href = l.get('href', '')
                full_link = f"https://bep.co.kr{href}" if href.startswith('/') else href
                if "idx=" not in full_link: continue
                
                clean_title = title_text.replace("모집중", "").strip()
                jobs.append(['BEP(워터)', clean_title, "공고 확인", full_link])
                
            # 중복 제거 (수집 단계)
            unique_jobs = []
            seen_links = set()
            for j in jobs:
                if j[3] not in seen_links:
                    unique_jobs.append(j)
                    seen_links.add(j[3])
            return unique_jobs
    except Exception as e:
        print(f"BEP 수집 중 오류: {e}")
        return []

def get_saramin_jobs(companies):
    """사람인 수집"""
    base_url = "https://www.saramin.co.kr/zf_user/search/recruit"
    jobs = []
    for company in companies:
        try:
            params = {'searchword': company, 'searchType': 'search'}
            res = requests.get(base_url, headers=HEADERS, params=params, timeout=15)
            soup = BeautifulSoup(res.text, 'html.parser')
            items = soup.select('.item_recruit')
            for item in items:
                co_tag = item.select_one('.corp_name a')
                if not co_tag: continue
                co_name = co_tag.text.strip()
                if company in co_name.replace("(주)", "").replace("주식회사", ""):
                    title_tag = item.select_one('.job_tit a')
                    conds = item.select('.job_condition span')
                    exp = conds[1].text.strip() if len(conds) > 1 else "상세 참조"
                    jobs.append([co_name, title_tag.text.strip(), exp, "https://www.saramin.co.kr" + title_tag['href']])
            time.sleep(1.2)
        except: continue
    return jobs

def safe_load_df(file_path, default_cols):
    """파일 로드 및 표준화 (중복 제거 포함)"""
    if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
        try:
            df = pd.read_csv(file_path, encoding='utf-8-sig')
            df.columns = [c.strip().replace('\ufeff', '') for c in df.columns]
            for col in default_cols:
                if col not in df.columns: df[col] = ""
            # 로드 시점에 이미 있는 중복 제거
            if 'link' in df.columns:
                df = df.drop_duplicates(subset=['link'], keep='first')
            return df[default_cols]
        except:
            return pd.DataFrame(columns=default_cols)
    return pd.DataFrame(columns=default_cols)

def main():
    saramin_targets = ["대영채비", "이브이시스", "플러그링크", "볼트업", "차지비", "에버온"]
    today = datetime.now().strftime('%Y-%m-%d')
    
    # 1. 데이터 로드
    df_master = safe_load_df("job_listings_all.csv", ['company', 'title', 'experience', 'link', 'first_seen'])
    df_ency = safe_load_df("encyclopedia.csv", ['link', 'company', 'title', 'content', 'last_updated'])
    df_comp = safe_load_df("Recruitment_completed.csv", ['company', 'title', 'experience', 'link', 'completed_date'])

    print(f"[{today}] 데이터 수집 시작...")
    scraped = get_bep_jobs() + get_saramin_jobs(saramin_targets)
    df_current = pd.DataFrame(scraped, columns=['company', 'title', 'experience', 'link'])

    if df_current.empty:
        print("수집된 데이터가 없습니다.")
    else:
        # 중복 제거 (현재 수집분 내)
        df_current = df_current.drop_duplicates(subset=['link'])

        # 2. 신규 공고 및 슬랙 알림
        # 이미 master에 있는 링크는 제외
        new_entries = df_current[~df_current['link'].isin(df_master['link'])].copy()
        
        if not new_entries.empty:
            new_entries['first_seen'] = today
            if SLACK_WEBHOOK_URL:
                msg = f"📢 *신규 채용 ({len(new_entries)}건)*\n"
                for _, r in new_entries.iterrows(): 
                    msg += f"• [{r['company']}] {r['title']} ({r['experience']})\n  <{r['link']}|보기>\n"
                requests.post(SLACK_WEBHOOK_URL, json={"text": msg})
            
            # 신규 데이터만 master에 추가
            df_master = pd.concat([df_master, new_entries], ignore_index=True).drop_duplicates(subset=['link'])

        # 3. 채용 종료 처리 (수집 대상 기업 중 현재 공고에 없는 것)
        active_cos = df_current['company'].unique()
        is_missing = ~df_master['link'].isin(df_current['link'])
        is_target_co = df_master['company'].isin(active_cos)
        
        closed = df_master[is_missing & is_target_co].copy()
        if not closed.empty:
            closed['completed_date'] = today
            # 완료 파일에 추가 후 중복 제거
            df_comp = pd.concat([df_comp, closed], ignore_index=True).drop_duplicates(subset=['link'])
            # Master에서 삭제
            df_master = df_master[~(is_missing & is_target_co)]

    # 4. Encyclopedia 업데이트 (본문/이미지 수집)
    # 내용이 부실하거나 없는 항목 추출
    retry_keywords = ["채용공고 상세", "본문 내용을 찾을 수 없습니다", "로그인", "상세 참조", "수집 실패"]
    
    # 기존 데이터 중 업데이트가 필요한 것
    df_ency['content'] = df_ency['content'].fillna("")
    is_bad = df_ency['content'].apply(lambda x: any(k in str(x) for k in retry_keywords) or len(str(x)) < 150)
    retry_links = df_ency[is_bad]['link'].tolist()
    
    # 아예 백과사전에 없는 신규 링크
    new_links = df_master[~df_master['link'].isin(df_ency['link'])]['link'].tolist()
    
    target_links = list(set(retry_links + new_links))

    if target_links:
        print(f"상세 내용/이미지 {len(target_links)}건 처리 중...")
        for link in target_links:
            # 원본 정보 찾기
            source = df_master[df_master['link'] == link]
            if source.empty: continue
            
            row = source.iloc[0]
            content = fetch_detail_content(link)
            
            if link in df_ency['link'].values:
                df_ency.loc[df_ency['link'] == link, ['content', 'last_updated']] = [content, today]
            else:
                new_row = pd.DataFrame([{
                    'link': link, 'company': row['company'], 'title': row['title'], 
                    'content': content, 'last_updated': today
                }])
                df_ency = pd.concat([df_ency, new_row], ignore_index=True)
        
        # 마지막으로 한 번 더 중복 제거
        df_ency = df_ency.drop_duplicates(subset=['link'], keep='last')

    # 5. 파일 저장
    df_master.to_csv("job_listings_all.csv", index=False, encoding='utf-8-sig')
    df_comp.to_csv("Recruitment_completed.csv", index=False, encoding='utf-8-sig')
    df_ency.to_csv("encyclopedia.csv", index=False, encoding='utf-8-sig')
    print(f"작업 완료. (현재 활성 공고: {len(df_master)}건)")

if __name__ == "__main__":
    main()
