import time
import random
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
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    return driver

def crawl_water_official(driver):
    """'워터' 공식 채용 페이지 수집 (bep.co.kr)"""
    print("--- [워터] 공식 홈페이지 수집 시작 ---")
    url = "https://bep.co.kr/Career/recruitment?type=3"
    results = []
    try:
        driver.get(url)
        # 페이지 로딩 대기
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CLASS_NAME, "recruitment-list")))
        
        # 공고 아이템 추출 (사이트 구조에 맞게 선택자 조정 필요)
        items = driver.find_elements(By.CSS_SELECTOR, ".recruitment-item") # 예시 선택자
        for item in items:
            title = item.find_element(By.CSS_SELECTOR, ".title").text.strip()
            results.append({
                'site': '공식홈',
                'company': '워터(BEP)',
                'title': title,
                'link': url
            })
    except Exception as e:
        print(f"워터 공식홈 수집 실패: {e}")
    return results

def crawl_portals():
    # '워터'를 제외한 나머지 경쟁사
    companies = ["대영채비", "이브이시스", "플러그링크", "볼트업", "차지비", "에버온"]
    results = []
    driver = get_driver()

    # 1. 워터 공식홈 데이터 먼저 추가
    results.extend(crawl_water_official(driver))

    for company in companies:
        print(f"--- {company} 포털 수집 시작 ---")
        
        # [사람인] 필터링 강화
        try:
            driver.get(f"https://www.saramin.co.kr/zf_user/search/recruit?searchword={company}")
            time.sleep(random.uniform(2, 4))
            items = driver.find_elements(By.CSS_SELECTOR, ".item_recruit")
            for item in items:
                corp = item.find_element(By.CSS_SELECTOR, ".corp_name a").text.strip()
                # '리워터', '넥스워터' 등을 거르기 위해 검색어와 회사명이 정확히 일치하거나 핵심을 포함하는지 확인
                if company in corp and len(corp) <= len(company) + 5: 
                    title_el = item.find_element(By.CSS_SELECTOR, ".job_tit a")
                    results.append({'site': '사람인', 'company': corp, 'title': title_el.text.strip(), 'link': title_el.get_attribute('href')})
        except: pass

        # [원티드] WebDriverWait 도입 및 선택자 점검
        try:
            driver.get(f"https://www.wanted.co.kr/search?query={company}&tab=position")
            # 요소가 나타날 때까지 명시적 대기
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, '[data-cy="post-card"]')))
            items = driver.find_elements(By.CSS_SELECTOR, '[data-cy="post-card"]')
            for item in items:
                corp = item.find_element(By.CSS_SELECTOR, '.job-card-company-name').text.strip()
                if company in corp:
                    title = item.find_element(By.CSS_SELECTOR, '.job-card-title').text.strip()
                    link = item.find_element(By.TAG_NAME, 'a').get_attribute('href')
                    results.append({'site': '원티드', 'company': corp, 'title': title, 'link': link})
        except: pass

        # [잡코리아] 구조 최적화
        try:
            driver.get(f"https://www.jobkorea.co.kr/Search/?stext={company}")
            time.sleep(3)
            # 잡코리아는 검색 결과가 iframe이나 별도 영역에 있을 수 있어 범용 선택자 사용
            items = driver.find_elements(By.CSS_SELECTOR, ".list-post .post, .item")
            for item in items:
                try:
                    corp = item.find_element(By.CSS_SELECTOR, ".name, .corp").text.strip()
                    if company in corp:
                        title_el = item.find_element(By.CSS_SELECTOR, ".title, .tit")
                        link = title_el.get_attribute('href') if title_el.tag_name == 'a' else title_el.find_element(By.TAG_NAME, 'a').get_attribute('href')
                        results.append({'site': '잡코리아', 'company': corp, 'title': title_el.text.strip(), 'link': link})
                except: continue
        except: pass

    driver.quit()
    
    # 중복 제거 및 저장
    if results:
        df = pd.DataFrame(results)
        df = df.drop_duplicates(subset=['company', 'title'], keep='first')
        df.to_csv("jobs.csv", index=False, encoding='utf-8-sig')
        print(f"✅ 최종 {len(df)}건 저장 완료")
    else:
        print("❌ 수집 데이터 없음")

if __name__ == "__main__":
    crawl_portals()
