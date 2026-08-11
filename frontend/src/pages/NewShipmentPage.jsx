import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { api } from '@/lib/api'

/*
 * Alta de un remito en draft (tarea 2.7): datos del receptor + productos.
 *
 * Los productos se van juntando en memoria y recién al guardar se persiste todo:
 * POST /api/shipments/ (tarea 2.1) y después un POST por ítem a
 * /api/shipments/{id}/items/ (tarea 2.2). Si el remito ya se creó y falla algún
 * ítem, el id queda guardado y los ítems ya subidos quedan marcados, así que
 * reintentar completa el remito en vez de crear uno nuevo duplicado.
 *
 * La cámara y el despacho son la tarea 2.8: acá el remito queda en draft.
 */
export function NewShipmentPage() {
  const navigate = useNavigate()

  const [receiverName, setReceiverName] = useState('')
  const [receiverEmail, setReceiverEmail] = useState('')
  const [receiverPhone, setReceiverPhone] = useState('')

  const [products, setProducts] = useState([])
  const [productsStatus, setProductsStatus] = useState('loading') // 'loading' | 'ready' | 'error'
  const [search, setSearch] = useState('')
  const [selectedProductId, setSelectedProductId] = useState(null)
  const [quantity, setQuantity] = useState('')
  const [notes, setNotes] = useState('')

  const [items, setItems] = useState([])
  const [createdShipmentId, setCreatedShipmentId] = useState(null)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)

  const loadProducts = useCallback(async () => {
    setProductsStatus('loading')
    try {
      const { data } = await api.get('/products/')
      setProducts(Array.isArray(data) ? data : (data.results ?? []))
      setProductsStatus('ready')
    } catch {
      setProductsStatus('error')
    }
  }, [])

  useEffect(() => {
    loadProducts()
  }, [loadProducts])

  const productsById = useMemo(
    () => new Map(products.map((product) => [product.id, product])),
    [products],
  )

  // Buscador del lado del cliente: el endpoint devuelve el catálogo completo de la
  // empresa (sin paginar), así que no hace falta ir al backend en cada tecla.
  const matches = useMemo(() => {
    const term = search.trim().toLowerCase()
    if (!term) return products
    return products.filter(
      (product) =>
        product.name.toLowerCase().includes(term) ||
        (product.barcode ?? '').toLowerCase().includes(term),
    )
  }, [products, search])

  const selectedProduct = selectedProductId == null ? null : productsById.get(selectedProductId)
  const quantityValue = Number(quantity)
  const canAddItem = Boolean(selectedProduct) && quantity !== '' && quantityValue > 0

  function handleAddItem() {
    if (!canAddItem) return
    setItems((current) => [
      ...current,
      {
        key: `${selectedProduct.id}-${Date.now()}`,
        productId: selectedProduct.id,
        quantity,
        notes: notes.trim(),
        saved: false,
      },
    ])
    setSelectedProductId(null)
    setQuantity('')
    setNotes('')
    setSearch('')
  }

  function handleRemoveItem(key) {
    setItems((current) => current.filter((item) => item.key !== key))
  }

  async function handleSubmit(event) {
    event.preventDefault()
    setError(null)
    setSubmitting(true)

    let shipmentId = createdShipmentId
    try {
      if (shipmentId == null) {
        const { data } = await api.post('/shipments/', {
          receiver_name: receiverName.trim(),
          receiver_email: receiverEmail.trim(),
          receiver_phone: receiverPhone.trim(),
        })
        shipmentId = data.id
        setCreatedShipmentId(shipmentId)
      }

      for (const item of items.filter((candidate) => !candidate.saved)) {
        await api.post(`/shipments/${shipmentId}/items/`, {
          product: item.productId,
          quantity: item.quantity,
          notes: item.notes,
        })
        // Marcado inmediato: si el siguiente ítem falla, un reintento no lo duplica.
        setItems((current) =>
          current.map((candidate) =>
            candidate.key === item.key ? { ...candidate, saved: true } : candidate,
          ),
        )
      }

      navigate('/', { replace: true })
    } catch {
      setError(
        shipmentId == null
          ? 'No se pudo crear el remito. Intentá de nuevo.'
          : `El remito #${shipmentId} se creó como borrador, pero no se pudieron agregar todos los productos. Tocá "Guardar borrador" para reintentar.`,
      )
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="min-h-svh">
      <header className="sticky top-0 z-10 border-b bg-background/95 backdrop-blur">
        <div className="mx-auto flex w-full max-w-2xl items-center justify-between gap-3 px-4 py-3">
          <h1 className="text-xl font-semibold">Nuevo remito</h1>
          <Button asChild variant="outline" className="h-12">
            <Link to="/">Cancelar</Link>
          </Button>
        </div>
      </header>

      <main className="mx-auto w-full max-w-2xl px-4 pt-4 pb-8">
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <Card className="gap-4 rounded-lg p-4">
            <CardHeader className="p-0">
              <CardTitle className="text-base">Receptor</CardTitle>
            </CardHeader>

            <CardContent className="flex flex-col gap-4 p-0">
              <div className="flex flex-col gap-2">
                <Label htmlFor="receiver-name">Nombre</Label>
                <Input
                  id="receiver-name"
                  name="receiver_name"
                  required
                  className="h-12"
                  value={receiverName}
                  onChange={(event) => setReceiverName(event.target.value)}
                />
              </div>

              <div className="flex flex-col gap-2">
                <Label htmlFor="receiver-email">Email</Label>
                <Input
                  id="receiver-email"
                  name="receiver_email"
                  type="email"
                  autoCapitalize="none"
                  className="h-12"
                  value={receiverEmail}
                  onChange={(event) => setReceiverEmail(event.target.value)}
                />
              </div>

              <div className="flex flex-col gap-2">
                <Label htmlFor="receiver-phone">Teléfono</Label>
                <Input
                  id="receiver-phone"
                  name="receiver_phone"
                  type="tel"
                  inputMode="tel"
                  className="h-12"
                  value={receiverPhone}
                  onChange={(event) => setReceiverPhone(event.target.value)}
                />
              </div>
            </CardContent>
          </Card>

          <Card className="gap-4 rounded-lg p-4">
            <CardHeader className="p-0">
              <CardTitle className="text-base">Productos</CardTitle>
            </CardHeader>

            <CardContent className="flex flex-col gap-4 p-0">
              {productsStatus === 'loading' && (
                <p className="text-sm text-muted-foreground">Cargando productos…</p>
              )}

              {productsStatus === 'error' && (
                <div className="flex flex-col items-start gap-3">
                  <p role="alert" className="text-sm text-destructive">
                    No se pudieron cargar los productos.
                  </p>
                  <Button type="button" variant="outline" className="h-12" onClick={loadProducts}>
                    Reintentar
                  </Button>
                </div>
              )}

              {productsStatus === 'ready' && products.length === 0 && (
                <p className="text-sm text-muted-foreground">
                  Tu empresa todavía no tiene productos cargados.
                </p>
              )}

              {productsStatus === 'ready' && products.length > 0 && (
                <>
                  <div className="flex flex-col gap-2">
                    <Label htmlFor="product-search">Buscar producto</Label>
                    <Input
                      id="product-search"
                      className="h-12"
                      placeholder="Nombre o código de barras"
                      value={search}
                      onChange={(event) => setSearch(event.target.value)}
                    />
                  </div>

                  {matches.length === 0 ? (
                    <p className="text-sm text-muted-foreground">
                      Ningún producto coincide con la búsqueda.
                    </p>
                  ) : (
                    <ul className="flex max-h-64 flex-col gap-2 overflow-y-auto">
                      {matches.map((product) => (
                        <li key={product.id}>
                          <Button
                            type="button"
                            variant={product.id === selectedProductId ? 'default' : 'outline'}
                            aria-pressed={product.id === selectedProductId}
                            data-product-id={product.id}
                            className="h-12 w-full justify-between"
                            onClick={() => setSelectedProductId(product.id)}
                          >
                            <span className="truncate">{product.name}</span>
                            {/* opacity-90, no 70: con el producto seleccionado el botón
                                es indigo y el blanco al 70% caía a 3.92 (WCAG AA pide 4.5). */}
                            <span className="text-xs opacity-90">{product.unit}</span>
                          </Button>
                        </li>
                      ))}
                    </ul>
                  )}

                  {selectedProduct && (
                    <div className="flex flex-col gap-4 border-t pt-4">
                      <div className="flex flex-col gap-2">
                        <Label htmlFor="item-quantity">
                          Cantidad ({selectedProduct.unit}) — {selectedProduct.name}
                        </Label>
                        <div className="flex items-center gap-2">
                          <Input
                            id="item-quantity"
                            type="number"
                            inputMode="decimal"
                            min="0"
                            step="0.01"
                            className="h-12"
                            value={quantity}
                            onChange={(event) => setQuantity(event.target.value)}
                          />
                          <span className="shrink-0 text-sm text-muted-foreground">
                            {selectedProduct.unit}
                          </span>
                        </div>
                      </div>

                      <div className="flex flex-col gap-2">
                        <Label htmlFor="item-notes">Notas</Label>
                        <Textarea
                          id="item-notes"
                          rows={2}
                          value={notes}
                          onChange={(event) => setNotes(event.target.value)}
                        />
                      </div>

                      <Button
                        type="button"
                        className="h-12"
                        disabled={!canAddItem}
                        onClick={handleAddItem}
                      >
                        Agregar producto
                      </Button>
                    </div>
                  )}
                </>
              )}

              {items.length > 0 && (
                <ul className="flex flex-col gap-2 border-t pt-4" data-testid="shipment-items">
                  {items.map((item) => {
                    const product = productsById.get(item.productId)
                    return (
                      <li
                        key={item.key}
                        className="flex items-start justify-between gap-3 rounded-md border p-3"
                      >
                        <div className="min-w-0">
                          <p className="truncate font-medium">{product?.name ?? 'Producto'}</p>
                          {/* La unidad va SIEMPRE junto a la cantidad (ej. "50 bolsas"). */}
                          <p className="text-sm text-muted-foreground">
                            {item.quantity} {product?.unit ?? ''}
                          </p>
                          {item.notes && (
                            <p className="text-sm text-muted-foreground">{item.notes}</p>
                          )}
                        </div>
                        {/* Un ítem ya guardado en el backend no se puede sacar desde acá:
                            se quitaría de la pantalla pero seguiría en el remito. */}
                        {!item.saved && (
                          <Button
                            type="button"
                            variant="outline"
                            className="h-12 shrink-0"
                            onClick={() => handleRemoveItem(item.key)}
                          >
                            Quitar
                          </Button>
                        )}
                      </li>
                    )
                  })}
                </ul>
              )}
            </CardContent>
          </Card>

          {error && (
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
          )}

          <Button type="submit" className="h-12 w-full" disabled={submitting}>
            {submitting ? 'Guardando…' : 'Guardar borrador'}
          </Button>
        </form>
      </main>
    </div>
  )
}
