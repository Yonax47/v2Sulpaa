// npm install --prefix <temporal> playwright; PLAYWRIGHT_MODULE=<temporal>/node_modules/playwright
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');

(async () => {
    const browser = await chromium.launch({channel: 'msedge', headless: true});
    const results = [];
    try {
        for (const width of [360, 390, 430, 768, 1440]) {
            const page = await browser.newPage({viewport: {width, height: 1000}});
            // APIs sintéticas: nunca se autentica ni se envían operaciones reales.
            await page.route('http://127.0.0.1:5067/**', async route => {
                const path = new URL(route.request().url()).pathname;
                if (path === '/operaciones/api/entregas/opciones') {
                    return route.fulfill({json: {ok: true, opciones: [
                        {tipo: 'RECOJO', nombre: 'Recojo en tienda', descripcion: 'Punto de prueba'},
                        {tipo: 'DELIVERY', nombre: 'Delivery', descripcion: 'Entrega de prueba'},
                    ]}});
                }
                if (path.includes('/api/') || path.startsWith('/api/')) {
                    return route.fulfill({json: {ok: true, carrito: {items: [{
                        carrito_detalle_id: 'fixture', nombre: 'Kombucha sintética para comprobar el carrito',
                        cantidad: 2, precio: 20, subtotal: 40, sabor: 'Café', presentacion: 'Botella 1 L',
                    }], subtotal: 40, cantidad_items: 2}, opciones: [], metodos_pago: []}});
                }
                return route.continue();
            });
            for (const route of ['login', 'registro', 'inicio', 'tienda', 'checkout', 'perfil', 'pedidos', 'dashboard', 'caja', 'inventario', 'historial', 'entregas', 'encuestas']) {
                const response = await page.goto(`http://127.0.0.1:5067/${route}`, {waitUntil: 'networkidle'});
                assert.equal(response.status(), 200, route);
                const data = await page.evaluate(() => {
                    const region = document.querySelector('[data-toast-region]');
                    const close = document.querySelector('[data-toast-close]');
                    const rect = close.getBoundingClientRect();
                    const outside = [...document.querySelectorAll('body *')].filter(el => {
                        const r = el.getBoundingClientRect();
                        return r.width > 0 && r.right > innerWidth + 1 && getComputedStyle(el).position !== 'fixed';
                    }).slice(0, 6).map(el => el.tagName + '.' + el.className);
                    return {scroll: document.documentElement.scrollWidth, width: innerWidth,
                        toastPosition: getComputedStyle(region).position, closeWidth: rect.width, closeHeight: rect.height, outside};
                });
                results.push({route, width, ...data});
                assert.ok(data.scroll <= width + 1, JSON.stringify(results.at(-1)));
                assert.equal(data.toastPosition, 'fixed');
                assert.ok(data.closeWidth >= 44 && data.closeHeight >= 44);
                const count = await page.evaluate(() => {
                    SulpaaToast.show('Mensaje único', 'success', {autoclose: false});
                    SulpaaToast.show('Mensaje único', 'success', {autoclose: false});
                    return [...document.querySelectorAll('[data-toast] p')].filter(p => p.textContent === 'Mensaje único').length;
                });
                assert.equal(count, 1);
                await page.locator('[data-toast-close]').last().click();
                if (route === 'tienda') {
                    await page.evaluate(() => SulpaaCart.open());
                    const drawer = page.locator('[data-cart-drawer]');
                    await drawer.waitFor({state: 'visible'});
                    await page.waitForFunction(() => document.querySelector('[data-cart-drawer]').getBoundingClientRect().right <= innerWidth + 1);
                    const rect = await drawer.boundingBox();
                    assert.ok(rect.x >= -1 && rect.x + rect.width <= width + 1, 'Carrito fuera de pantalla');
                    await page.locator('[data-cart-close]').click();
                }
                if (route === 'dashboard' || route === 'caja' || route === 'encuestas') {
                    for (const canvas of await page.locator('canvas:visible').all()) {
                        const rect = await canvas.boundingBox();
                        assert.ok(rect && rect.width > 0 && rect.width <= width, 'Gráfico sin tamaño adaptable');
                    }
                }
                if (width === 390 && ['login', 'checkout', 'dashboard', 'caja'].includes(route) && process.env.VISUAL_OUTPUT) {
                    await page.screenshot({path: `${process.env.VISUAL_OUTPUT}/${route}-390.png`, fullPage: true});
                }
            }
            await page.close();
        }
        console.log(JSON.stringify({passed: results.length, widths: [360, 390, 430, 768, 1440],
            checks: ['overflow', 'toast fixed', 'close 44px', 'deduplication', 'cart drawer', 'canvas bounds']}, null, 2));
    } finally { await browser.close(); }
})().catch(error => {console.error(error); process.exitCode = 1;});
