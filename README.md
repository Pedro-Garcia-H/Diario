# El Diario de Pedro (versión automática)

Este programa arma tu diario todas las mañanas sin usar inteligencia artificial. Lee los titulares de los medios por RSS, el clima de la zona 21, el tipo de cambio del Banguat, las efemérides de Wikipedia y lo más buscado en Google. Con eso arma una página con el mismo diseño de tu diario.

Corre solo, gratis, en GitHub. No necesitás tener la computadora prendida.

## Qué trae

1. **Nacionales**: Prensa Libre, La Hora, República, Publinews e Infobae, más las "Cortitas".
2. **Para leer con calma**: reportajes de Plaza Pública y Agencia Ocote.
3. **Internacionales**: BBC Mundo y DW.
4. **Deportes**: Guatefutbol, Emisoras Unidas, Infobae y Marca. Comunicaciones va primero.
5. **Ciencia y tecnología**: NASA y ScienceDaily (en inglés) y Xataka.
6. **El día en datos**: el clima con 3 días de pronóstico, el tipo de cambio, un día como hoy y lo más buscado en Google.

Arriba, el recuadro **Ojo con esto** aparece solo cuando un medio habla de cortes de agua o luz en tu zona, de alertas del clima o de convocatorias del TSE.

El programa también:

- esconde la nota roja,
- quita las noticias repetidas entre medios,
- y guarda un archivo con los diarios de días anteriores.

## Lo que no hace (porque no usa IA)

- Los resúmenes son las primeras líneas que publica cada medio, con su tono.
- No escribe análisis, recomendaciones ni la tabla de obras.
- El orden de las noticias sale de reglas fijas: palabras que suben o bajan una noticia, el medio y la hora. No hay criterio humano.

## Cómo ponerlo a andar (una sola vez, unos 15 minutos)

### 1. Crear la cuenta y el repositorio

1. Entrá a https://github.com y creá una cuenta gratis.
2. Arriba a la derecha, tocá **+** y luego **New repository**.
3. En el nombre poné `diario`, marcá **Public** y tocá **Create repository**.
   La versión gratis de GitHub solo publica páginas de repositorios públicos, así que tu diario tendrá una dirección pública. Nadie la va a encontrar si no se la das. Aun así, no pongás datos privados en `config.py`.

### 2. Subir los archivos

1. En tu repositorio nuevo, tocá **uploading an existing file**.
2. Arrastrá estos archivos: `diario.py`, `config.py`, `estilo.css`, `requirements.txt` y `README.md`.
3. Tocá **Commit changes**.

### 3. Crear la tarea automática

La carpeta `.github` está oculta en muchas computadoras, así que este archivo se crea a mano:

1. Tocá **Add file** y luego **Create new file**.
2. En el nombre escribí exactamente esto: `.github/workflows/diario.yml`
3. Copiá y pegá todo el contenido del archivo `diario.yml` que te mandé.
4. Tocá **Commit changes**.

### 4. Armar el primer diario

1. Andá a la pestaña **Actions**.
2. A la izquierda, elegí **Armar el diario**.
3. Tocá **Run workflow** y otra vez **Run workflow**.
4. Esperá uno o dos minutos hasta que salga la palomita verde.

### 5. Publicarlo como página

1. Andá a **Settings** y luego a **Pages**.
2. En **Branch** elegí `main` y la carpeta `/docs`, y tocá **Save**.
3. En un par de minutos aparece arriba la dirección, algo como `https://TU-USUARIO.github.io/diario/`. Guardala en tus favoritos.

Listo. Desde mañana se arma solo a las 5:37 a. m. Si querés que salga a otra hora, cambiá la línea `cron` en `diario.yml`. La hora va en UTC: hay que sumarle 6 a la hora de Guatemala.

## Cómo cambiar cosas

Todo se cambia en **`config.py`**. En GitHub, abrí el archivo, tocá el lápiz para editarlo y luego **Commit changes**.

- **Medios**: en `SECCIONES` podés agregar o quitar feeds.
- **Qué va primero**: en `PRIORIDAD`, cada palabra suma puntos. Por ejemplo, `"comunicaciones": 10`.
- **Nota roja**: en `NOTA_ROJA` está la lista de palabras que esconden una nota.
- **Ojo con esto**: en `ALERTAS` están las palabras que mandan una nota al recuadro de arriba.
- **Frases**: en `FRASES` están los refranes. Cambian solos cada día.
- **Cumpleaños**: en `CUMPLEANOS`, con este formato: `("Ronald", 14, 3),`

Python es delicado con las comillas y las comas. Si el diario deja de salir después de un cambio, en la pestaña **Actions** vas a ver una X roja. Lo más probable es que falte una coma o unas comillas.

## Si algo falla

- **Un medio cambia o quita su feed.** El diario igual sale, y al pie dice "No pude leer [medio]". Buscá la nueva dirección del feed o quitá ese medio de `config.py`.
- **GitHub pausa la tarea.** A veces lo hace en repositorios que tienen mucho tiempo sin cambios. Si te llega un correo de GitHub avisando, entrá a **Actions** y volvé a activarla.
- **Querés armarlo en ese momento.** Usá **Actions**, luego **Armar el diario** y **Run workflow**.

## Probarlo en tu computadora (opcional)

Con Python 3.10 o más reciente:

```
pip install -r requirements.txt
python diario.py
```

Después abrí `docs/index.html` en el navegador.
