import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime
import time
import re
import os
from urllib.parse import urljoin

# --- 환경 설정 ---
SLACK_WEBHOOK_URL = os.environ.get('SLACK_WEBHOOK_URL')
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
    'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
}

def safe_load_df(file_path, default_cols):
    """파일 로드 시 컬럼 보장 및 중복/공백 제거"""
    if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
        try:
            df = pd.read_csv(file_path, encoding='utf-8-sig', on_bad_lines='skip')
            df.columns = [c.strip().replace('\ufeff', '') for c in df.columns]
            # link 컬럼 데이터 정제 및 중복 제거
            if 'link' in df.columns:
                df['link'] = df['link'].astype(str).str.strip()
                df = df.drop_duplicates(subset=['link'], keep='first')
            # 없는 컬럼 생성
            for col in default_cols:
                if col not in df.columns: df[col] = ""
            return df[default_cols]
        except Exception as e:
            print(f"로드 실패({file_path}): {e}")
            return pd.DataFrame(columns=default_cols)
    return pd.DataFrame(columns=default_cols)

def fetch_detail_content(url):
    """상세 본문 추출 (텍스트 우선, 부족하면 이미지)"""
    try:
        time.sleep(1)
        res = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(res.text, 'html.parser')
        # 불필요 태그 제거
        for tag in soup(["script", "style", "nav", "footer", "header", "button"]): tag.decompose()

        # 본문 영역 탐색
        content_area = soup.select_one('.user_content, .recruit_view_cont, .view_con, .job_detail, body')
        text_content = content_area.get_text(separator="\n", strip=True) if content_area else ""
        
        # 텍스트가 너무 짧으면 이미지 수집
        if len(text_content) < 150 and content_area:
            imgs = content_area.find_all('img')
            img_urls = [urljoin(url, i.get('src') or i.get('data-src')) for i in imgs if i.get('src') or i.get('data-src')]
            clean_imgs = [i for i in img_urls if not any(x in i.lower() for x in ["icon", "logo", "common"])]
            if clean_imgs: return "[이미지 공고] " + ", ".join(clean_imgs)

        return text_content[:15000] if len(text_content) > 50 else "상세 링크 참조"
    except: return "수집 실패"

def get_bep_jobs():
    """BEP(워터) 수집: 더 유연한 태그 탐색 적용"""
    url = "https://bep.co.kr/Career/recruitment?type=3"
    jobs = []
    try:
        res = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # 1. <a> 태그 내 recruitmentView 패턴 찾기
        links = soup.find_all('a', href=re.compile(r'recruitmentView'))
        
        # 2. 만약 안 찾아진다면, 전체 텍스트에서 '워터'가 포함된 tr/li 탐색
        if not links:
            rows = soup.find_all(['tr', 'li'])
            for row in rows:
                if "워터" in row.get_text() or "전기차" in row.get_text():
                    a_tag = row.find('a')
                    if a_tag: links.append(a_tag)

        for l in links:
            href = l.get('href', '')
            full_link = urljoin("https://bep.co.kr", href).strip()
            title = l.get_text(" ", strip=True).replace("모집중", "").strip()
            
            if not title or title in ["목록", "이전", "다음"]: continue
            # 중복 방지 (수집 단계)
            if any(j[3] == full_link for j in jobs): continue
            
            jobs.append(['BEP(워터)', title, "공고 확인", full_link])
    except Exception as e:
        print(f"BEP 수집 오류: {e}")
    return jobs

def get_saramin_jobs(companies):
    """사람인 수집"""
    base_url = "https://www.saramin.co.kr/zf_user/search/recruit"
    jobs = []
    for company in companies:
        try:
            params = {'searchword': company, 'searchType': 'search'}
            res = requests.get(base_url, headers=HEADERS, params=params, timeout=15)
            soup = BeautifulSoup(res.text, 'html.parser')
            for item in soup.select('.item_recruit'):
                co_tag = item.select_one('.corp_name a')
                if co_tag and company in co_tag.text.replace(" ", ""):
                    title_tag = item.select_one('.job_tit a')
                    conds = item.select('.job_condition span')
                    exp = conds[1].text.strip() if len(conds) > 1 else "경력무관"
                    jobs.append([co_tag.text.strip(), title_tag.text.strip(), exp, ("https://www.saramin.co.kr" + title_tag['href']).strip()])
            time.sleep(1)
        except: continue
    return jobs

def main():
    today = datetime.now().strftime('%Y-%m-%d')
    
    # 1. 기존 데이터 로드
    df_master = safe_load_df("job_listings_all.csv", ['company', 'title', 'experience', 'link', 'first_seen'])
    df_ency = safe_load_df("encyclopedia.csv", ['link', 'company', 'title', 'content', 'last_updated'])
    df_comp = safe_load_df("Recruitment_completed.csv", ['company', 'title', 'experience', 'link', 'completed_date'])

    print(f"[{today}] 수집 시작...")
    targets = ["대영채비", "이브이시스", "플러그링크", "볼트업", "차지비", "에버온"]
    scraped_data = get_bep_jobs() + get_saramin_jobs(targets)
    df_current = pd.DataFrame(scraped_data, columns=['company', 'title', 'experience', 'link'])
    df_current['link'] = df_current['link'].str.strip()
    df_current = df_current.drop_duplicates(subset=['link'])

    # 2. 신규 공고 알림 및 master 업데이트
    new_entries = df_current[~df_current['link'].isin(df_master['link'])].copy()
    if not new_entries.empty:
        new_entries['first_seen'] = today
        if SLACK_WEBHOOK_URL:
            msg = f"📢 *신규 채용 ({len(new_entries)}건)*\n"
            for _, r in new_entries.iterrows():
                msg += f"• [{r['company']}] {r['title']}\n  <{r['link']}|보기>\n"
            requests.post(SLACK_WEBHOOK_URL, json={"text": msg})
        df_master = pd.concat([df_master, new_entries], ignore_index=True)

    # 3. 채용 종료 처리 (수정됨)
    # 로직: 마스터에는 있으나 현재 수집본에 없고, 해당 회사의 검색 결과가 최소 1개라도 나왔을 때만 종료 처리
    active_links = df_current['link'].tolist()
    successfully_scraped_companies = df_current['company'].unique()
    
    # 마스터에서 사라진 링크들 중, 수집에 성공한 기업의 것만 필터링
    is_missing = ~df_master['link'].isin(active_links)
    is_target_company = df_master['company'].isin(successfully_scraped_companies)
    
    closed_jobs = df_master[is_missing & is_target_company].copy()
    
    if not closed_jobs.empty:
        closed_jobs['completed_date'] = today
        df_comp = pd.concat([df_comp, closed_jobs], ignore_index=True)
        # 마스터에서 제거
        df_master = df_master[~(is_missing & is_target_company)]

    # 4. Encyclopedia 업데이트
    if 'link' in df_ency.columns:
        retry_keywords = ["수집 실패", "로그인", "상세 링크 참조"]
        is_bad = df_ency['content'].fillna("").apply(lambda x: any(k in str(x) for k in retry_keywords) or len(str(x)) < 150)
        
        # 보완이 필요한 링크 + 아예 없는 링크
        target_links = df_ency[is_bad]['link'].tolist() + df_master[~df_master['link'].isin(df_ency['link'])]['link'].tolist()
        target_links = list(set(target_links))

        if target_links:
            print(f"상세 수집 중... ({len(target_links)}건)")
            for link in target_links:
                info = df_master[df_master['link'] == link]
                if info.empty: continue
                content = fetch_detail_content(link)
                if link in df_ency['link'].values:
                    df_ency.loc[df_ency['link'] == link, ['content', 'last_updated']] = [content, today]
                else:
                    new_row = pd.DataFrame([{'link': link, 'company': info.iloc[0]['company'], 'title': info.iloc[0]['title'], 'content': content, 'last_updated': today}])
                    df_ency = pd.concat([df_ency, new_row], ignore_index=True)

    # 5. 중복 제거, 정렬 및 저장
    # 모든 DataFrame에서 최종적으로 중복 제거 및 link 공백 제거
    for df in [df_master, df_comp, df_ency]:
        if 'link' in df.columns:
            df['link'] = df['link'].astype(str).str.strip()
            df.drop_duplicates(subset=['link'], keep='first', inplace=True)

    # Encyclopedia 회사명 기준 내림차순 정렬
    if 'company' in df_ency.columns:
        df_ency = df_ency.sort_values(by='company', ascending=False)

    df_master.to_csv("job_listings_all.csv", index=False, encoding='utf-8-sig')
    df_comp.to_csv("Recruitment_completed.csv", index=False, encoding='utf-8-sig')
    df_ency.to_csv("encyclopedia.csv", index=False, encoding='utf-8-sig')
    print(f"작업 완료. (현재 공고: {len(df_master)}건, 종료 공고: {len(df_comp)}건, 백과사전: {len(df_ency)}건)")

if __name__ == "__main__":
    main()
