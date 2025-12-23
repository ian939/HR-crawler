import time
import re
import random
from datetime import datetime
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

def get_driver():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    driver.set_page_load_timeout(45) # 타임아웃을 조금 더 여유있게 설정
    return driver

def extract_exp(text):
    """텍스트에서 경력 연차를 찾아 '경력N↑' 형태로 반환. 없으면 None 반환"""
    if not text: return None
    
    # 'N년', 'N~M년' 형태 추출
    match = re.search(r'(\d+)년', text)
    if match:
        return f"경력{match.group(1)}↑"
    if "신입" in text:
        return "신입"
    return None # 명시적으로 경력이 없으면 null(None) 처리

def crawl_bep_official(driver):
    """'워터' 공식홈페이지 수집 (경력 없어도 포함)"""
    print(">>> [워터] 공식홈페이지 수집 중...")
    url = "https://bep.co.kr/Career/recruitment?type=3"
    results = []
    try:
        driver.get(url)
        # 페이지 로딩을 위해 10초간 충분히 대기
        time.sleep(10)
        
        # 이전에 성공했던 텍스트 기반 수집 로직 강화
        # '모집중', '시니어', '주니어' 등 키워드가 포함된 요소를 찾음
        items = driver.find_elements(By.XPATH, "//*[contains(text(), '모집중') or contains(text(), '시니어') or contains(text(), '주니어')]")
        
        seen_titles = set()
        for item in items:
            title_text = item.text.strip().replace('\n', ' ')
            # 유효한 길이의 제목이고 중복이 아닐 경우
            if 10 < len(title_text) < 100 and title_text not in seen_titles:
                exp = extract_exp(title_text)
                results.append({
                    'site': '공식홈',
                    'company': '워터(BEP)',
                    'title': title_text,
                    'experience': exp, # 경력이 없으면 여기서 None(null)이 들어감
                    'link': url
                })
                seen_titles.add(title_text)
        print(f"  - 워터(BEP): {len(results)}건 수집 완료")
    except Exception as e:
        print(f"  - BEP 수집 오류: {e}")
    return results

def crawl_all():
    # 포털 검색 리스트 (워터는 노이즈 방지를 위해 제외)
    companies = ["대영채비", "이브이시스", "플러그링크", "볼트업", "차지비", "에버온"]
    results = []
    driver = get_driver()

    # 1. 워터 공식홈 수집 실행
    results.extend(crawl_bep_official(driver))

    # 2. 나머지 포털 사이트 수집
    for company in companies:
        print(f"\n>>> [{company}] 수집 시작")
        
        # [사람인]
        try:
            driver.get(f"https://www.saramin.co.kr/zf_user/search/recruit?searchword={company}")
            time.sleep(3)
            elements = driver.find_elements(By.CSS_SELECTOR, ".item_recruit")
            for el in elements[:10]:
                corp = el.find_element(By.CSS_SELECTOR, ".corp_name").text.strip()
                if company in corp:
                    title = el.find_element(By.CSS_SELECTOR, ".job_tit").text.strip()
                    exp_info = el.find_element(By.CSS_SELECTOR, ".job_condition").text
                    results.append({
                        'site': '사람인', 'company': corp, 'title': title,
                        'experience': extract_exp(exp_info),
                        'link': el.find_element(By.CSS_SELECTOR, ".job_tit a").get_attribute('href')
                    })
        except: pass

        # [원티드]
        try:
            driver.get(f"https://www.wanted.co.kr/search?query={company}&tab=position")
            time.sleep(5)
            items = driver.find_elements(By.CSS_SELECTOR, '[data-cy="post-card"]')
            for item in items[:10]:
                corp = item.find_element(By.CSS_SELECTOR, '.job-card-company-name').text.strip()
                if company in corp:
                    title = item.find_element(By.CSS_SELECTOR, '.job-card-title').text.strip()
                    results.append({
                        'site': '원티드', 'company': corp, 'title': title,
                        'experience': extract_exp(item.text),
                        'link': item.find_element(By.TAG_NAME, 'a').get_attribute('href')
                    })
        except: pass

        # [잡코리아]
        try:
            driver.get(f"https://www.jobkorea.co.kr/Search/?stext={company}")
            time.sleep(5)
            posts = driver.find_elements(By.CSS_SELECTOR, ".list-post .post")
            for p in posts[:10]:
                corp = p.find_element(By.CSS_SELECTOR, ".name").text.strip()
                if company in corp:
                    title = p.find_element(By.CSS_SELECTOR, ".title").text.strip()
                    try:
                        exp_info = p.find_element(By.CSS_SELECTOR, ".exp, .option").text
                    except: exp_info = None
                    results.append({
                        'site': '잡코리아', 'company': corp, 'title': title,
                        'experience': extract_exp(exp_info),
                        'link': p.find_element(By.CSS_SELECTOR, "a.title").get_attribute('href')
                    })
        except: pass

    driver.quit()

    if results:
        df = pd.DataFrame(results).drop_duplicates(subset=['company', 'title'])
        # 컬럼 순서 고정
        df = df[['site', 'company', 'title', 'experience', 'link']]
        
        # 파일명에 현재 날짜 반영 (예: jobs_20241223.csv)
        filename = f"jobs_{datetime.now().strftime('%Y%m%d')}.csv"
        df.to_csv(filename, index=False, encoding='utf-8-sig')
        print(f"\n✅ 완료: {filename} 저장 ({len(df)}건)")
    else:
        print("\n❌ 수집된 데이터가 없습니다.")

if __name__ == "__main__":
    crawl_all()
