/*
============================================================
SULPAA V2 - HOME CLIENTE
============================================================

Responsabilidades:
- Animaciones de entrada al hacer scroll.
- Aparición progresiva de tarjetas.
- Animación inicial del Hero.
- Efecto suave de movimiento en productos.
- Respeto por preferencias de accesibilidad.

IMPORTANTE:
Este archivo solo controla comportamiento visual.
No contiene lógica de negocio.
============================================================
*/


document.addEventListener("DOMContentLoaded", () => {

    /*
    ==========================================================
    1. DETECTAR PREFERENCIA DE MOVIMIENTO REDUCIDO
    ==========================================================
    */

    const reduceMotion = window.matchMedia(
        "(prefers-reduced-motion: reduce)"
    ).matches;


    /*
    ==========================================================
    2. ELEMENTOS CON ANIMACIÓN DE ENTRADA
    ==========================================================
    */

    const revealElements = document.querySelectorAll(".reveal");


    /*
    Si el usuario prefiere reducir movimiento,
    mostramos todo inmediatamente.
    */

    if (reduceMotion) {

        revealElements.forEach((element) => {
            element.classList.add("is-visible");
        });

        return;
    }


    /*
    ==========================================================
    3. INTERSECTION OBSERVER
    ==========================================================

    IntersectionObserver detecta cuándo un elemento
    comienza a entrar en la pantalla.

    Es más eficiente que ejecutar cálculos
    continuamente durante el scroll.
    ==========================================================
    */

    const revealObserver = new IntersectionObserver(

        (entries, observer) => {

            entries.forEach((entry) => {

                /*
                Si todavía no está visible,
                no hacemos nada.
                */

                if (!entry.isIntersecting) {
                    return;
                }


                /*
                Activamos la animación.
                */

                entry.target.classList.add("is-visible");


                /*
                La animación solo ocurre una vez.

                Después de aparecer, dejamos de observar
                el elemento.
                */

                observer.unobserve(entry.target);

            });

        },

        {
            threshold: 0.12,

            /*
            Hace que la animación empiece un poco antes
            de que el elemento esté completamente visible.
            */

            rootMargin: "0px 0px -35px 0px"
        }

    );


    /*
    Empezamos a observar todos los elementos
    que tienen la clase .reveal
    */

    revealElements.forEach((element) => {
        revealObserver.observe(element);
    });



    /*
    ==========================================================
    4. ANIMACIÓN INICIAL DEL HERO
    ==========================================================

    El Hero es visible apenas carga la página,
    así que queremos que aparezca rápidamente
    sin esperar demasiado al observer.
    ==========================================================
    */

    const heroElements = document.querySelectorAll(
        ".home-hero .reveal"
    );


    window.requestAnimationFrame(() => {

        setTimeout(() => {

            heroElements.forEach((element, index) => {

                setTimeout(() => {

                    element.classList.add("is-visible");

                }, index * 120);

            });

        }, 100);

    });



    /*
    ==========================================================
    5. MOVIMIENTO SUAVE DE LAS BOTELLAS DEL HERO
    ==========================================================

    Aplicamos una pequeña sensación de flotación.

    No es una animación agresiva.
    Solo ayuda a que el producto se sienta más vivo.
    ==========================================================
    */

    const heroBottles = document.querySelectorAll(
        ".hero-bottle"
    );


    heroBottles.forEach((bottle, index) => {

        /*
        Alternamos el tiempo para que ambas botellas
        no se muevan exactamente igual.
        */

        const duration = index % 2 === 0
            ? 4200
            : 4700;


        bottle.animate(

            [
                {
                    transform:
                        bottle.classList.contains(
                            "hero-bottle-cafe"
                        )
                            ? "rotate(-10deg) translateY(0)"
                            : "rotate(10deg) translateY(0)"
                },

                {
                    transform:
                        bottle.classList.contains(
                            "hero-bottle-cafe"
                        )
                            ? "rotate(-8deg) translateY(-8px)"
                            : "rotate(8deg) translateY(-8px)"
                },

                {
                    transform:
                        bottle.classList.contains(
                            "hero-bottle-cafe"
                        )
                            ? "rotate(-10deg) translateY(0)"
                            : "rotate(10deg) translateY(0)"
                }
            ],

            {
                duration: duration,
                iterations: Infinity,
                easing: "ease-in-out"
            }

        );

    });



    /*
    ==========================================================
    6. MOVIMIENTO SUAVE DE LAS BOTELLAS
       DE "ARMA TU PACK"
    ==========================================================
    */

    const customPackBottles = document.querySelectorAll(
        ".custom-bottle"
    );


    customPackBottles.forEach((bottle, index) => {

        bottle.animate(

            [
                {
                    translate: "0 0"
                },

                {
                    translate:
                        index % 2 === 0
                            ? "0 -7px"
                            : "0 -4px"
                },

                {
                    translate: "0 0"
                }
            ],

            {
                duration:
                    4200 + (index * 250),

                iterations:
                    Infinity,

                easing:
                    "ease-in-out"
            }

        );

    });



    /*
    ==========================================================
    7. EFECTO SUAVE EN TARJETAS DE SABORES
    ==========================================================

    Cuando el cursor entra en una tarjeta,
    la botella recibe una pequeña profundidad adicional.

    CSS ya controla el hover principal.
    JS solo agrega un pequeño desplazamiento dinámico.
    ==========================================================
    */

    const flavorCards = document.querySelectorAll(
        ".flavor-showcase"
    );


    flavorCards.forEach((card) => {

        const bottle = card.querySelector(
            ".flavor-product img"
        );


        if (!bottle) {
            return;
        }


        card.addEventListener("mousemove", (event) => {

            /*
            Calculamos la posición horizontal del cursor
            respecto de la tarjeta.
            */

            const rect = card.getBoundingClientRect();

            const x =
                event.clientX - rect.left;

            const center =
                rect.width / 2;


            /*
            Movimiento máximo muy pequeño:
            aproximadamente 3 grados.
            */

            const rotation =
                ((x - center) / center) * 3;


            bottle.style.transform =
                `translateY(-8px)
                 scale(1.035)
                 rotate(${rotation}deg)`;

        });


        card.addEventListener("mouseleave", () => {

            /*
            Limpiamos el estilo inline para que
            el CSS vuelva a controlar la animación.
            */

            bottle.style.transform = "";

        });

    });



    /*
    ==========================================================
    8. SCROLL SUAVE PARA ENLACES INTERNOS
    ==========================================================

    Actualmente algunos botones apuntan a secciones
    de la misma página:

    #sabores
    #packs
    #suscripciones

    Con este comportamiento el desplazamiento
    se siente más natural.
    ==========================================================
    */

    const internalLinks = document.querySelectorAll(
        'a[href^="#"]:not([href="#"])'
    );


    internalLinks.forEach((link) => {

        link.addEventListener("click", (event) => {

            const targetId =
                link.getAttribute("href");


            const target =
                document.querySelector(targetId);


            if (!target) {
                return;
            }


            event.preventDefault();


            /*
            Calculamos una pequeña compensación
            por el navbar sticky.
            */

            const navbar =
                document.querySelector(".site-header");


            const navbarHeight =
                navbar
                    ? navbar.offsetHeight
                    : 0;


            const targetPosition =
                target.getBoundingClientRect().top
                + window.scrollY
                - navbarHeight
                - 16;


            window.scrollTo({

                top:
                    targetPosition,

                behavior:
                    "smooth"

            });

        });

    });

});