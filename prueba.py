from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import pickle
import time
import os
import json

COOKIES_FILE = "ig_cookies.pkl"

# ================== CONFIGURACIÓN DEL DRIVER ==================

def crear_driver_con_cookies(headless=False):
    chrome_options = Options()
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")

    if headless:
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--disable-gpu")

    driver = webdriver.Chrome(options=chrome_options)
    return driver

# ================== MANEJO DE SESIÓN CON COOKIES ==================

def guardar_cookies(driver):
    with open(COOKIES_FILE, "wb") as f:
        pickle.dump(driver.get_cookies(), f)
    print("Cookies guardadas.")

def cargar_cookies(driver):
    driver.get("https://www.instagram.com/")
    with open(COOKIES_FILE, "rb") as f:
        cookies = pickle.load(f)
    for c in cookies:
        c.pop("sameSite", None)
        driver.add_cookie(c)
    driver.refresh()
    print("Sesión restaurada desde cookies.")

def iniciar_sesion_con_cookies(driver):
    if os.path.exists(COOKIES_FILE):
        cargar_cookies(driver)
        return

    print("[LOGIN] No hay cookies. Abriendo página de login de Instagram...")
    driver.get("https://www.instagram.com/accounts/login/")
    print("[LOGIN] Inicia sesión manualmente en la ventana de Instagram.")
    print("[LOGIN] Voy a esperar hasta que detecte la cookie 'sessionid' (máx. 5 minutos).")

    max_wait_seconds = 300
    interval = 5
    checks = max_wait_seconds // interval
    logged_in = False

    for i in range(checks):
        time.sleep(interval)
        cookies = driver.get_cookies()
        has_session = any(c.get("name") == "sessionid" for c in cookies)
        print(f"[LOGIN] Chequeo {i+1}/{checks} - sessionid presente: {has_session}")
        if has_session:
            logged_in = True
            break

    if not logged_in:
        raise Exception("No se detectó que hayas iniciado sesión en el tiempo esperado.")

    guardar_cookies(driver)

# ================== EXTRACCIÓN DE LISTA DE SEGUIDOS ==================

def extraer_lista_seguidos(driver, username: str, max_scrolls=60, max_cuentas=10):
    username = username.strip().lstrip("@")
    print(f"\n[EXTRACCIÓN] Accediendo a perfil de: {username}")
    print(f"[EXTRACCIÓN] Límite configurado: {max_cuentas} cuentas máximas")
    
    driver.get(f"https://www.instagram.com/{username}/")
    WebDriverWait(driver, 15).until(
        EC.presence_of_element_located((By.TAG_NAME, "header"))
    )
    time.sleep(3)

    print("[EXTRACCIÓN] Localizando y abriendo modal de seguidos...")
    following_link = WebDriverWait(driver, 15).until(
        EC.element_to_be_clickable(
            (By.XPATH, f"//a[contains(@href, '/{username}/following/')]")
        )
    )
    driver.execute_script("arguments[0].click();", following_link)
    time.sleep(4)

    dialog = WebDriverWait(driver, 15).until(
        EC.presence_of_element_located((By.XPATH, "//div[@role='dialog']"))
    )
    cont = dialog.find_element(
        By.XPATH, ".//div[contains(@style,'overflow') or contains(@class,'_aano')]"
    )

    raw_usernames = []
    unique_before = 0
    no_change = 0
    limite_alcanzado = False

    for i in range(max_scrolls):
        user_elements = cont.find_elements(By.XPATH, ".//a[contains(@href,'/')]")
        print(f"[EXTRACCIÓN] Scroll {i+1}: {len(user_elements)} elementos detectados")

        for el in user_elements:
            href = el.get_attribute("href")
            if not href or "/p/" in href or "instagram.com" not in href:
                continue
            uname = href.rstrip("/").split("/")[-1]
            if uname == username or uname.startswith("?"):
                continue
            raw_usernames.append(uname)
        
        # Limpiar duplicados temporalmente para verificar límite
        temp_unique = list(dict.fromkeys(raw_usernames))
        if len(temp_unique) >= max_cuentas:
            print(f"[EXTRACCIÓN] Límite alcanzado: {len(temp_unique)} cuentas únicas")
            raw_usernames = temp_unique[:max_cuentas]  # Cortar al límite
            limite_alcanzado = True
            break

        unique_now = len(set(raw_usernames))
        if unique_now == unique_before:
            no_change += 1
            print(f"[EXTRACCIÓN] Sin nuevos seguidos ({no_change}/5)")
        else:
            no_change = 0
            unique_before = unique_now

        if no_change >= 5:
            print("[EXTRACCIÓN] No aparecen nuevos seguidos. Fin del scroll.")
            break

        if user_elements:
            driver.execute_script("arguments[0].scrollIntoView();", user_elements[-1])

        time.sleep(2)
        
        if limite_alcanzado:
            break

    print("\n[EXTRACCIÓN] Limpiando duplicados...")
    clean_usernames = list(dict.fromkeys(raw_usernames))
    
    # Asegurar que no exceda el límite después de limpiar duplicados
    if len(clean_usernames) > max_cuentas:
        clean_usernames = clean_usernames[:max_cuentas]
        print(f"[EXTRACCIÓN] Recortado a {max_cuentas} cuentas después de limpiar duplicados")

    following_list = [
        {"username": u, "profile_url": f"https://www.instagram.com/{u}/"}
        for u in clean_usernames
    ]

    print(f"[EXTRACCIÓN] Total seguidos únicos extraídos: {len(following_list)}")
    return following_list

# ================== EXTRACCIÓN DE DATOS DE PERFIL INDIVIDUAL ==================

def obtener_info_perfil_completa(driver, username: str) -> dict:
    username = username.strip().lstrip("@")
    url = f"https://www.instagram.com/{username}/"
    
    print(f"[PERFIL] Accediendo a: {url}")
    driver.get(url)
    
    WebDriverWait(driver, 15).until(
        EC.presence_of_element_located((By.TAG_NAME, "header"))
    )
    time.sleep(2)
    
    data = {
        "nombre_completo": None,
        "usuario": username,
        "biografia": None,
        "tipo_cuenta": None,
        "categoria": None,
        "seguidores": 0,
        "seguidos": 0,
        "enlace_perfil": url,
        "scraped_at": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    
    try:
        try:
            usuario_element = driver.find_element(By.CSS_SELECTOR, "h1._ab1a")
            data["usuario"] = usuario_element.text.strip()
        except:
            pass
        
        try:
            spans = driver.find_elements(By.CSS_SELECTOR, "span.x1lliihq.x1plvlek")
            for span in spans:
                text = span.text.strip()
                if text and text != data["usuario"]:
                    unwanted = ["publicaciones", "seguidores", "seguidos", "Seguir", 
                               "Message", "Enviar mensaje", "Message", "Siguiendo"]
                    if not any(unw in text.lower() for unw in unwanted):
                        if not text.replace(",", "").replace(".", "").replace("mil", "").strip().isdigit():
                            data["nombre_completo"] = text
                            break
        except:
            pass
        
        try:
            number_elements = driver.find_elements(By.CSS_SELECTOR, "span.html-span.xdj266r.x14z9mp.xat24cr.x1lziwak.xexx8yu")
            
            if len(number_elements) >= 3:
                def parse_instagram_number(text):
                    if not text:
                        return 0
                    text = text.lower().replace("mil", "k").replace("k", "000")
                    text = text.replace(",", ".").replace(" ", "")
                    import re
                    match = re.search(r"(\d+(?:\.\d+)?)", text)
                    if match:
                        num = float(match.group(1))
                        if "000" in text:
                            num = int(num * 1000)
                        return int(num)
                    return 0
                
                seguidores_text = number_elements[1].text.strip() if len(number_elements) > 1 else "0"
                data["seguidores"] = parse_instagram_number(seguidores_text)
                
                seguidos_text = number_elements[2].text.strip() if len(number_elements) > 2 else "0"
                data["seguidos"] = parse_instagram_number(seguidos_text)
            
            if data["seguidores"] == 0 or data["seguidos"] == 0:
                page_text = driver.page_source.lower()
                import re
                seguidores_match = re.search(r'(\d[\d\.,]*\s*(?:mil|k)?)\s*seguidores', page_text, re.IGNORECASE)
                if seguidores_match:
                    data["seguidores"] = parse_instagram_number(seguidores_match.group(1))
                seguidos_match = re.search(r'(\d[\d\.,]*\s*(?:mil|k)?)\s*seguidos', page_text, re.IGNORECASE)
                if seguidos_match:
                    data["seguidos"] = parse_instagram_number(seguidos_match.group(1))
                    
        except:
            pass
        
        try:
            categoria_element = driver.find_element(By.CSS_SELECTOR, "div._ap3a._aaco._aacu._aacy._aad6._aade")
            data["categoria"] = categoria_element.text.strip()
        except:
            pass
        
        try:
            bio_element = driver.find_element(By.CSS_SELECTOR, "span._ap3a._aaco._aacu._aacx._aad7._aade")
            data["biografia"] = bio_element.text.strip()
        except:
            try:
                bio_divs = driver.find_elements(By.CSS_SELECTOR, "div._ap3a._aaco._aacu._aacy._aad6._aade")
                for div in bio_divs:
                    text = div.text.strip()
                    if text and text != data.get("categoria", ""):
                        if len(text.split()) > 2:
                            data["biografia"] = text
                            break
            except:
                pass
        
        try:
            page_html = driver.page_source.lower()
            if "business" in page_html or "empresa" in page_html:
                data["tipo_cuenta"] = "empresa"
            elif "creator" in page_html or "creador" in page_html or "public figure" in page_html:
                data["tipo_cuenta"] = "creador"
            elif "personal" in page_html or "personal blog" in page_html:
                data["tipo_cuenta"] = "personal"
        except:
            pass
        
    except Exception as e:
        print(f"[ERROR] Error extrayendo datos de {username}: {str(e)}")
    
    return data

# ================== PROCESAR MÚLTIPLES PERFILES EN PARALELO ==================

def procesar_perfiles_multi_tabs(driver, seguidos_list, num_tabs=5):
    """
    Procesa múltiples perfiles usando varias pestañas para mayor velocidad.
    """
    print(f"\n[PROCESO] Extrayendo información de {len(seguidos_list)} perfiles ({num_tabs} pestañas)...")
    
    # Guardar pestaña original
    base_handle = driver.current_window_handle
    
    # Crear pestañas adicionales
    for _ in range(num_tabs - 1):
        driver.execute_script("window.open('about:blank','_blank');")
    
    window_handles = driver.window_handles
    if len(window_handles) < num_tabs:
        num_tabs = len(window_handles)
    
    print(f"[PROCESO] Usando {num_tabs} pestañas para procesamiento paralelo.")
    
    resultados = []
    
    for idx, seguido in enumerate(seguidos_list):
        tab_index = idx % num_tabs
        handle = window_handles[tab_index]
        
        # Cambiar a la pestaña correspondiente
        driver.switch_to.window(handle)
        
        username = seguido["username"]
        print(f"[PROCESO] [{idx+1}/{len(seguidos_list)}] Tab {tab_index+1} -> @{username}")
        
        # Extraer información del perfil
        info = obtener_info_perfil_completa(driver, username)
        
        # Combinar con datos básicos
        resultado = seguido.copy()
        resultado.update(info)
        resultados.append(resultado)
        
        print(f"  ✓ Nombre: {info['nombre_completo'] or 'N/A'}")
        print(f"  ✓ Seguidores: {info['seguidores']}, Seguidos: {info['seguidos']}")
        
        # Pausa breve entre requests
        time.sleep(1.5)
    
    # Regresar a la pestaña original
    driver.switch_to.window(base_handle)
    
    return resultados

# ================== GUARDAR RESULTADOS ==================

def guardar_resultados(resultados, username_target):

    import json
    import csv
    
    # Guardar JSON
    json_filename = f"seguidos_info_{username_target}.json"
    with open(json_filename, "w", encoding="utf-8") as f:
        json.dump(resultados, f, ensure_ascii=False, indent=2)
    print(f"\n[ARCHIVO] Datos guardados en JSON: {json_filename}")
    
    # Guardar CSV
    csv_filename = f"seguidos_info_{username_target}.csv"
    if resultados:
        fieldnames = resultados[0].keys()
        with open(csv_filename, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(resultados)
        print(f"[ARCHIVO] Datos guardados en CSV: {csv_filename}")
    
    return json_filename, csv_filename

# ================== MAIN ==================

def main():
    driver = crear_driver_con_cookies()
    target_username = "esedgarcia"

    try:
        # 1. Iniciar sesión
        iniciar_sesion_con_cookies(driver)
        
        # 2. Extraer lista de seguidos
        seguidos = extraer_lista_seguidos(driver, target_username, max_scrolls=60)
        
        # Guardar lista inicial
        with open(f"seguidos_{target_username}.txt", "w", encoding="utf-8") as f:
            for user in seguidos:
                f.write(f"{user['username']}\n")
        print(f"\n[ARCHIVO] Lista básica guardada en: seguidos_{target_username}.txt")
        
        # 3. Extraer información detallada de cada perfil seguido
        if seguidos:
            print(f"\n[PROCESO] Iniciando extracción detallada de {len(seguidos)} perfiles...")
            resultados = procesar_perfiles_multi_tabs(driver, seguidos, num_tabs=3)
            
            # 4. Guardar resultados
            guardar_resultados(resultados, target_username)
            
            # 5. Mostrar resumen
            print("\n[RESUMEN] Datos extraídos:")
            print(f"Total perfiles procesados: {len(resultados)}")
            
            # Mostrar primeros 5 resultados
            print("\nPrimeros 5 perfiles:")
            for i, res in enumerate(resultados[:5], 1):
                print(f"{i}. @{res['usuario']} - {res['nombre_completo'] or 'Sin nombre'}")
                print(f"   Seguidores: {res['seguidores']}, Seguidos: {res['seguidos']}")
        else:
            print("\n[ADVERTENCIA] No se encontraron seguidos para procesar.")
            
    except Exception as e:
        print(f"\n[ERROR] Error en el proceso principal: {str(e)}")
    finally:
        driver.quit()

if __name__ == "__main__":
    main()