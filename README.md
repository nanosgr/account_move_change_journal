# Account Move Change Journal

## Descripción

Este módulo permite cambiar el diario de transacciones contables (account.move) de forma segura, recalculando automáticamente todos los campos necesarios para mantener la integridad de la información contable.

## Características

- **Wizard intuitivo**: Interfaz simple para seleccionar el diario destino
- **Cambio masivo**: Permite cambiar múltiples transacciones a la vez
- **Validaciones**: Verifica que el cambio sea posible antes de ejecutarlo
- **Advertencias**: Muestra información sobre posibles conflictos
- **Auditoría**: Registra todos los cambios en el chatter de cada transacción
- **Renumeración automática**: Opción para asignar nueva secuencia según el diario destino
- **Seguridad**: Solo usuarios con permisos de "Account Manager" o "Account User" pueden ejecutarlo

## Uso

### Desde la vista de formulario

1. Abrir una transacción contable (Facturas, Asientos, etc.)
2. Hacer clic en el botón **"Change Journal"** en el header
3. Seleccionar el diario destino
4. Configurar las opciones:
   - **Reset Sequence**: Genera una nueva secuencia del diario destino
   - **Force Change**: Forzar el cambio aunque haya advertencias (usar con precaución)
5. Hacer clic en **"Change Journal"**

### Desde la vista de lista (masivo)

1. Seleccionar múltiples transacciones en la vista de lista
2. Hacer clic en **Acción → Change Journal**
3. Seguir los mismos pasos del punto anterior

## Validaciones

El módulo realiza las siguientes validaciones:

- Verifica que se haya seleccionado un diario destino
- Comprueba que no todas las transacciones ya pertenezcan al diario destino
- Para transacciones publicadas con hash (locked), requiere activar "Force Change"
- Valida que el tipo de diario sea compatible con el tipo de transacción

## Advertencias

El wizard muestra advertencias en los siguientes casos:

- Transacciones ya publicadas (posted)
- Transacciones con líneas conciliadas
- Transacciones de diferentes diarios de origen
- Incompatibilidad entre tipo de diario y tipo de transacción
- Múltiples tipos de transacciones seleccionadas

## Campos recalculados

Al cambiar el diario, el módulo actualiza:

- `journal_id`: El nuevo diario
- `name`: Nueva secuencia si se activa "Reset Sequence"
- Campos computados que dependen de `journal_id` (automáticamente por Odoo)

## Auditoría

Cada cambio queda registrado en el chatter de la transacción con:

- Nombre del diario anterior
- Nombre del diario nuevo
- Cambio de secuencia (si aplica)

## Permisos

- **account.group_account_manager**: Acceso completo
- **account.group_account_user**: Acceso completo

## Notas técnicas

- El módulo utiliza el contexto `check_move_validity=False` para permitir cambios temporales
- El contexto `skip_invoice_sync` evita sincronizaciones innecesarias durante el cambio
- Manejo de errores individual por transacción para evitar fallos en operaciones masivas

## Desarrollo futuro

En una fase posterior se implementará:

- Acción de servidor para automatización mediante scripts
- Integración con flujos de trabajo personalizados

## Dependencias

- `account`: Módulo de contabilidad de Odoo

## Autor

Vikingo Software SAS

## Licencia

AGPL-3
