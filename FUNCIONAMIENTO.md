# Account Move Change Journal - Resumen de Funcionamiento

## Descripción General

Este módulo permite cambiar el diario contable de asientos (`account.move`) y sus pagos relacionados (`account.payment`), manteniendo la integridad de datos entre ambos modelos.

## Funcionalidad Principal

### Wizard: `account.move.change.journal`

Permite seleccionar uno o más asientos contables y cambiarlos a un nuevo diario.

### Flujo de Operación

1. **Selección de asientos**: El usuario selecciona los `account.move` a modificar
2. **Validaciones previas**:
   - Verifica que los asientos no estén en el mismo diario destino
   - Advierte sobre asientos publicados, reconciliados o con hash
   - Verifica compatibilidad de tipos de diario
3. **Detección de pagos relacionados**: Busca `account.payment` vinculados via `move_id`
4. **Cambio de pagos PRIMERO**: Se procesan los pagos antes que los moves para evitar conflictos de sincronización
5. **Cambio de asientos**: Se actualizan los `account.move`

## Manejo de `account.payment`

### Problema Resuelto

En Odoo 18, existe una sincronización automática `Payment → Move` que puede causar conflictos:
- El método `_synchronize_to_moves` intenta escribir campos readonly en moves publicados
- Esto genera errores como: "No puede modificar los siguientes campos de solo lectura en un movimiento publicado: date, partner_id, currency_id, line_ids"

### Solución Implementada

Se usa **SQL directo** para actualizar el payment, evitando:
- El método `write()` de `account.payment`
- La sincronización `_synchronize_to_moves`
- Recomputaciones no deseadas

### Campos Actualizados en Payment

```sql
UPDATE account_payment
SET journal_id = <nuevo_journal>,
    payment_method_line_id = <metodo_pago_compatible>,
    receiptbook_id = <talonario_correspondiente>,
    is_reconciled = false,
    write_date = NOW(),
    write_uid = <usuario>
WHERE id = <payment_id>
```

### Reset de Reconciliación

Al cambiar el diario de un pago, se realiza un reset completo de la reconciliación en el siguiente orden:

1. **Eliminación de conciliaciones parciales**: Se eliminan todos los registros de `account.partial.reconcile` asociados a las líneas del pago
2. **Reset de `is_reconciled`**: Se establece en `false`

Esto produce los siguientes efectos en los campos computed (del módulo `account_payment_pro`):
- `unmatched_amount` = valor anterior de `matched_amount` (el monto queda disponible)
- `matched_move_line_ids` = vacío (sin líneas conciliadas)
- `matched_amount` = 0
- `matched_amount_untaxed` = 0

Esta operación es necesaria porque:
- El pago ya no está asociado a las mismas líneas contables del diario original
- Se debe volver a reconciliar el pago en el nuevo diario
- Evita inconsistencias en el estado de reconciliación
- Los campos `matched_*` son computed (no stored) y se recalculan automáticamente al eliminar las conciliaciones parciales

### Lógica de Selección

#### Payment Method Line
1. Busca método con mismo código Y cuenta outstanding configurada
2. Si no existe, busca método con mismo código
3. Si no existe, busca cualquier método con cuenta outstanding
4. Si no existe, usa el primer método disponible

#### Receiptbook
1. Verifica que no sea transferencia interna
2. Verifica que la compañía use receiptbooks (`use_receiptbook`)
3. Busca receiptbook por `partner_type` y `company_id`

## Validaciones y Advertencias

### Errores Bloqueantes
- No hay asientos seleccionados
- No hay diario destino
- Todos los asientos ya están en el diario destino
- Diario destino sin métodos de pago configurados
- Métodos de pago sin cuenta outstanding y sin defaults de compañía

### Advertencias Informativas
- Asientos publicados
- Asientos con líneas reconciliadas
- Asientos de diferentes diarios origen
- Diferentes tipos de asiento
- Incompatibilidad de tipo de diario
- Pagos relacionados que serán modificados

## Contextos Especiales Utilizados

- `check_move_validity=False`: Evita validaciones de integridad del move
- `skip_invoice_sync=True`: Evita sincronización con facturas
- `skip_account_move_synchronization=True`: Evita sincronización inversa

## Dependencias

- `account`: Módulo base de contabilidad
- `account_payment_pro_receiptbook` (opcional): Para manejo de talonarios

## Configuración Requerida

Para que el cambio funcione correctamente, el diario destino debe tener:

1. **Métodos de pago configurados** (entrantes/salientes según corresponda)
2. **Cuentas de pagos pendientes** (outstanding accounts) en:
   - Los métodos de pago del diario, O
   - Los valores por defecto de la compañía

## Auditoría

Se registra en el chatter de cada registro modificado:
- Diario anterior y nuevo
- Cambio de secuencia (si aplica)
- Indicación de actualización automática (para pagos)

## Versiones

- **18.0.1.0.0**: Versión inicial
- **18.0.1.1.0**: Corrección de sincronización Payment ↔ Move
- **18.0.1.2.0**: Soporte para `receiptbook_id` en pagos
- **18.0.1.3.0**: Reset de `is_reconciled` a False al cambiar diario del pago
- **18.0.1.4.0**: Desconciliación completa del pago: elimina `account.partial.reconcile` para resetear `matched_amount`, `matched_move_line_ids`, `unmatched_amount` y `matched_amount_untaxed`
