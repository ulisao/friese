/*
 * Escaneo de código de barras con la cámara en el alta/edición de Product del
 * Django Admin. El admin de empresa hoy tiene que tipear el `barcode` a mano
 * (tarea 11.1); esto agrega un botón "Escanear código" al lado del campo que
 * abre la cámara, decodifica en vivo y llena el campo con lo que leyó — el
 * admin confirma ("Usar este código") o vuelve a escanear si salió mal, y
 * recién ahí guarda el producto con el botón normal del formulario.
 *
 * Mismo par de librerías que ya usa el escaneo del operador en el frontend
 * (frontend/src/components/BarcodeScanner.jsx, tareas 11.3/11.4), pero acá el
 * Admin no tiene bundler: se vendorean sueltas en admin/js/vendor/ y se cargan
 * como <script> clásico (exponen los globals `jsQR` y `Quagga`).
 *
 *   - admin/js/vendor/jsQR.js       — jsQR 1.4.0 (Apache-2.0), QR en vivo,
 *     corre en cada frame.
 *   - admin/js/vendor/quagga.min.js — @ericblade/quagga2 1.12.1 (MIT), para
 *     EAN-13/EAN-8/Code128 (los códigos de barras reales de una mercadería,
 *     no solo QR). `decodeSingle` relee la imagen entera cada vez que se lo
 *     llama, así que se dispara cada QUAGGA_INTERVAL_MS y solo cuando jsQR no
 *     encontró nada en ese frame — tirarlo en cada frame saturaría la CPU sin
 *     ganar nada.
 *   Para actualizar cualquiera de las dos: pisar el archivo con la versión
 *   nueva del paquete correspondiente en frontend/node_modules (mismas que
 *   declara frontend/package.json) y confirmar que siguen exponiendo esos
 *   globals.
 *
 * A diferencia del escaneo del operador, acá no hay backend de por medio: se
 * detecta un código, se muestra, y el admin decide. Por eso no hace falta
 * cooldown ni relock — apenas se detecta algo el loop se pausa entero hasta
 * que el admin confirma, reintenta o cancela.
 *
 * Resolución y throttle (mismo ajuste que en el frontend, BarcodeScanner.jsx):
 * sin tope de resolución la cámara puede entregar cuadros mucho más grandes
 * de lo necesario, y decodificar eso en CADA frame (hasta 60/seg) satura el
 * hilo principal — la cámara y el resto de la página se sienten lentos. Se
 * pide 1280x720 (de sobra para un código a la distancia a la que se lo
 * apunta) y el decode se throttlea a SCAN_INTERVAL_MS: el ojo no nota la
 * diferencia entre 60 y ~8 intentos por segundo, pero el hilo principal sí.
 *
 * Recorte al reticle: sin esto, jsQR/Quagga analizan el FRAME ENTERO, así que
 * cualquier número o texto que quede alrededor del código dentro del cuadro
 * (una etiqueta con tablas, otro código impreso cerca) es candidato a
 * "detectado" tanto como el código real. La solución es que las dos
 * librerías reciban SOLO los píxeles que caen dentro del reticle rojo.
 *
 * El <video> usa `object-fit: contain` (ver barcode_scan.css), así que la
 * imagen se ve completa pero con letterbox si el aspect ratio del contenedor
 * no coincide con el de la cámara — el reticle está posicionado en pantalla
 * relativo al contenedor, no al frame nativo. `computeCropRect` deshace ese
 * letterbox para traducir el rectángulo del reticle (coordenadas de
 * pantalla) a coordenadas de píxel del video nativo, que es lo que hace
 * falta para recortar con `drawImage`.
 */
(function () {
  'use strict'

  var SCAN_INTERVAL_MS = 120
  var QUAGGA_INTERVAL_MS = 450
  var QUAGGA_READERS = ['ean_reader', 'ean_8_reader', 'code_128_reader']

  function computeCropRect(video, reticleEl) {
    var videoRect = video.getBoundingClientRect()
    var reticleRect = reticleEl.getBoundingClientRect()
    var videoAspect = video.videoWidth / video.videoHeight
    var boxAspect = videoRect.width / videoRect.height

    var displayWidth, displayHeight, offsetX, offsetY
    if (boxAspect > videoAspect) {
      displayHeight = videoRect.height
      displayWidth = displayHeight * videoAspect
      offsetX = (videoRect.width - displayWidth) / 2
      offsetY = 0
    } else {
      displayWidth = videoRect.width
      displayHeight = displayWidth / videoAspect
      offsetX = 0
      offsetY = (videoRect.height - displayHeight) / 2
    }

    var scale = video.videoWidth / displayWidth
    var x = (reticleRect.left - videoRect.left - offsetX) * scale
    var y = (reticleRect.top - videoRect.top - offsetY) * scale
    var w = reticleRect.width * scale
    var h = reticleRect.height * scale

    // Clamp: si algo dio un valor fuera de rango (redondeos, un layout
    // todavía no asentado), mejor un recorte un poco corrido que un
    // `drawImage` con dimensiones inválidas, que tira excepción y corta el
    // loop de escaneo.
    var clampedX = Math.max(0, Math.min(x, video.videoWidth - 1))
    var clampedY = Math.max(0, Math.min(y, video.videoHeight - 1))
    return {
      x: clampedX,
      y: clampedY,
      w: Math.max(1, Math.min(w, video.videoWidth - clampedX)),
      h: Math.max(1, Math.min(h, video.videoHeight - clampedY)),
    }
  }

  function init() {
    var triggers = document.querySelectorAll('[data-barcode-scan-trigger]')
    if (!triggers.length) return

    var overlay = buildOverlay()
    document.body.appendChild(overlay.root)

    triggers.forEach(function (trigger) {
      trigger.addEventListener('click', function () {
        var field = trigger.closest('.barcode-scan-field')
        var input = field && field.querySelector('[data-barcode-scan-input]')
        if (input) overlay.open(input)
      })
    })
  }

  function buildOverlay() {
    var root = document.createElement('div')
    root.className = 'barcode-scan-overlay'
    root.hidden = true

    var videoWrap = document.createElement('div')
    videoWrap.className = 'barcode-scan-video-wrap'

    var video = document.createElement('video')
    video.setAttribute('autoplay', '')
    video.setAttribute('playsinline', '')
    video.muted = true

    var reticle = document.createElement('div')
    reticle.className = 'barcode-scan-reticle'

    var status = document.createElement('p')
    status.className = 'barcode-scan-status'

    var result = document.createElement('div')
    result.className = 'barcode-scan-result'
    result.hidden = true

    var resultCode = document.createElement('div')
    resultCode.className = 'barcode-scan-result-code'

    var resultActions = document.createElement('div')
    resultActions.className = 'barcode-scan-result-actions'

    var useButton = document.createElement('button')
    useButton.type = 'button'
    useButton.className = 'button default'
    useButton.textContent = 'Usar este código'

    var retryButton = document.createElement('button')
    retryButton.type = 'button'
    retryButton.className = 'button'
    retryButton.textContent = 'Volver a escanear'

    resultActions.appendChild(useButton)
    resultActions.appendChild(retryButton)
    result.appendChild(resultCode)
    result.appendChild(resultActions)

    videoWrap.appendChild(video)
    videoWrap.appendChild(reticle)
    videoWrap.appendChild(status)
    videoWrap.appendChild(result)

    var footer = document.createElement('div')
    footer.className = 'barcode-scan-footer'
    var cancelButton = document.createElement('button')
    cancelButton.type = 'button'
    cancelButton.className = 'button'
    cancelButton.textContent = 'Cancelar'
    footer.appendChild(cancelButton)

    root.appendChild(videoWrap)
    root.appendChild(footer)

    var canvas = document.createElement('canvas')
    var ctx = canvas.getContext('2d', { willReadFrequently: true })

    var state = {
      input: null,
      stream: null,
      rafId: null,
      paused: false,
      quaggaBusy: false,
      lastQuaggaAt: 0,
      lastScanAt: 0,
      cropRect: null,
    }

    function recomputeCropRect() {
      if (!root.hidden && video.videoWidth) {
        state.cropRect = computeCropRect(video, reticle)
      }
    }
    window.addEventListener('resize', recomputeCropRect)
    window.addEventListener('orientationchange', recomputeCropRect)

    function setStatus(text, isError) {
      status.textContent = text || ''
      status.hidden = !text
      status.classList.toggle('is-error', !!isError)
    }

    function stopCamera() {
      if (state.rafId) cancelAnimationFrame(state.rafId)
      state.rafId = null
      if (state.stream) {
        state.stream.getTracks().forEach(function (track) {
          track.stop()
        })
      }
      state.stream = null
    }

    function close() {
      stopCamera()
      root.hidden = true
      state.input = null
      result.hidden = true
      setStatus('')
    }

    function onDetected(code) {
      state.paused = true
      resultCode.textContent = code
      result.hidden = false
    }

    function tick() {
      var now = Date.now()
      if (!state.paused && video.videoWidth && now - state.lastScanAt >= SCAN_INTERVAL_MS) {
        state.lastScanAt = now
        if (!state.cropRect) state.cropRect = computeCropRect(video, reticle)
        var crop = state.cropRect
        canvas.width = crop.w
        canvas.height = crop.h
        ctx.drawImage(video, crop.x, crop.y, crop.w, crop.h, 0, 0, crop.w, crop.h)
        var imageData = ctx.getImageData(0, 0, canvas.width, canvas.height)
        var qrResult = window.jsQR
          ? window.jsQR(imageData.data, imageData.width, imageData.height)
          : null
        if (qrResult && qrResult.data) {
          onDetected(qrResult.data)
        } else if (window.Quagga && !state.quaggaBusy) {
          if (now - state.lastQuaggaAt >= QUAGGA_INTERVAL_MS) {
            state.lastQuaggaAt = now
            state.quaggaBusy = true
            window.Quagga.decodeSingle({
              src: canvas.toDataURL('image/jpeg', 0.8),
              numOfWorkers: 0,
              locate: true,
              decoder: { readers: QUAGGA_READERS },
            })
              .then(function (quaggaResult) {
                var code = quaggaResult && quaggaResult.codeResult && quaggaResult.codeResult.code
                if (code) onDetected(code)
              })
              .catch(function () {})
              .finally(function () {
                state.quaggaBusy = false
              })
          }
        }
      }
      state.rafId = requestAnimationFrame(tick)
    }

    function open(input) {
      state.input = input
      state.paused = false
      state.cropRect = null
      result.hidden = true
      setStatus('Abriendo la cámara…')
      root.hidden = false

      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        setStatus('Este navegador no permite usar la cámara (hace falta https).', true)
        return
      }

      navigator.mediaDevices
        .getUserMedia({
          video: {
            facingMode: { ideal: 'environment' },
            width: { ideal: 1280 },
            height: { ideal: 720 },
          },
          audio: false,
        })
        .then(function (stream) {
          if (root.hidden) {
            stream.getTracks().forEach(function (track) {
              track.stop()
            })
            return
          }
          state.stream = stream
          video.srcObject = stream
          setStatus('Apuntá al código')
          state.rafId = requestAnimationFrame(tick)
        })
        .catch(function (error) {
          setStatus(
            error && error.name === 'NotAllowedError'
              ? 'No se pudo acceder a la cámara: falta el permiso del navegador.'
              : 'No se pudo abrir la cámara del dispositivo.',
            true,
          )
        })
    }

    useButton.addEventListener('click', function () {
      if (state.input) {
        state.input.value = resultCode.textContent
        state.input.dispatchEvent(new Event('input', { bubbles: true }))
        state.input.dispatchEvent(new Event('change', { bubbles: true }))
      }
      close()
    })

    retryButton.addEventListener('click', function () {
      result.hidden = true
      state.paused = false
      setStatus('Apuntá al código')
    })

    cancelButton.addEventListener('click', close)

    return { root: root, open: open }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init)
  } else {
    init()
  }
})()
