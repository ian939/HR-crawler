import time
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
    options.add_argument("--headless=new") # 최신 헤드리스 모드
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    # 자동화 감지 우회 핵심 설정
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    # 타임아웃 설정 (사이트 하나당 최대 30초 이상 걸리지 않게 함)
    driver.set_page_load_timeout(30)
    return driver

def crawl_bep_official(driver):
    """'워터' 공식홈페이지 전용 (가장 정확)"""
    print(">>> [워터] 공식홈페이지 수집 중...")
    try:
        driver.get("https://bep.co.kr/Career/recruitment?type=3")
        # 리스트 로딩을 위해 7초간 확실히 대기
        time.sleep(7)
        
        # BEP 사이트는 텍스트가 담긴 요소를 넓게 검색
        items = driver.find_elements(By.CSS_SELECTOR, "div, p, span")
        results = []
        for item in items:
            text = item.text.strip()
            # 채용 공고 제목인 것 같은 것만 필터링 (예: '매니저', '엔지니어' 등 포함)
            if any(keyword in text for keyword in ['매니저', '엔지니어', '담당', '팀장', '모집']):
                if len(text) > 5 and len(text) < 50:
                    results.append({'site': '공식홈', 'company': '워터(BEP)', 'title': text, 'link': driver.current_url})
        return results
    except Exception as e:
        print(f"!!! BEP 수집 오류: {e}")
        return []

def crawl_portals():
    # 포털에서는 '워터'를 제외 (이미지에서 본 노이즈 제거 목적)
    companies = ["대영채비", "이브이시스", "플러그링크", "볼트업", "차지비", "에버온"]
    results = []
    driver = get_driver()

    # 1. 워터 공식홈
    results.extend(crawl_bep_official(driver))

    for company in companies:
        print(f"\n>>> [{company}] 수집 시작")
        
        # [사람인]
        try:
            driver.get(f"https://www.saramin.co.kr/zf_user/search/recruit?searchword={company}")
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CLASS_NAME, "item_recruit")))
            items = driver.find_elements(By.CSS_SELECTOR, ".item_recruit")
            for item in items[:5]: # 상위 5개만
                corp = item.find_element(By.CSS_SELECTOR, ".corp_name").text
                if company in corp:
                    title = item.find_element(By.CSS_SELECTOR, ".job_tit").text
                    link = item.find_element(By.CSS_SELECTOR, ".job_tit a").get_attribute('href')
                    results.append({'site': '사람인', 'company': corp, 'title': title, 'link': link})
        except: print(f"  - 사람인 {company} 실패")

        # [원티드] - 차단 가능성 높음, 명시적 대기 필수
        try:
            driver.get(f"https://www.wanted.co.kr/search?query={company}&tab=position")
            time.sleep(5) # 스크롤 및 로딩 대기
            items = driver.find_elements(By.CSS_SELECTOR, '[data-cy="post-card"]')
            for item in items[:5]:
                corp = item.find_element(By.CSS_SELECTOR, '.job-card-company-name').text
                if company in corp:
                    title = item.find_element(By.CSS_SELECTOR, '.job-card-title').text
                    link = item.find_element(By.TAG_NAME, 'a').get_attribute('href')
                    results.append({'site': '원티드', 'company': corp, 'title': title, 'link': link})
        except: print(f"  - 원티드 {company} 실패")

        # [잡코리아]
        try:
            driver.get(f"https://www.jobkorea.co.kr/Search/?stext={company}")
            time.sleep(5)
            items = driver.find_elements(By.CSS_SELECTOR, ".list-post .post")
            for item in items[:5]:
                corp = item.find_element(By.CSS_SELECTOR, ".name").text
                if company in corp:
                    title = item.find_element(By.CSS_SELECTOR, ".title").text
                    link = item.find_element(By.CSS_SELECTOR, ".title").get_attribute('href')
                    results.append({'site': '잡코리아', 'company': corp, 'title': title, 'link': link})
        except: print(f"  - 잡코리아 {company} 실패")

    driver.quit()
    
    # 중복 제거 및 저장
    df = pd.DataFrame(results).drop_duplicates(subset=['company', 'title'])
    df.to_csv("jobs.csv", index=False, encoding='utf-8-sig')
    print(f"\n✅ 수집 완료: 총 {len(df)}건")

if __name__ == "__main__":
    crawl_portals()
