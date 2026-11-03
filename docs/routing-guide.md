# Support routing guide

You work on the support team of a mid-size online store that sells home goods: lamps, kettles, bedding, rugs, furniture and kitchenware. The store and its customers are simulated for this project.

Every incoming ticket gets four things: a **queue**, an **urgency**, the **order id** (if there is one) and whether the customer **wants a refund**. People on the team route tickets by this guide. Your system has to route them the same way.

## Queues

| Queue | What goes there |
|---|---|
| `billing` | Payments and charges: double charges, failed payments, wrong amounts, charges for an order that was already cancelled, invoices and receipts, promo codes that didn't apply, and refunds that are late after a return was already accepted. |
| `shipping` | Delivery: where is my order, tracking, delays, "delivered" but not received, changing the address of an order that has already shipped. |
| `returns` | Sending something back: return or exchange requests, return labels, and items that arrived damaged, broken, defective or wrong. |
| `order_changes` | Changing or cancelling an order that has **not shipped yet**: address, size, colour, quantity, adding or removing items. |
| `product` | Questions about a product, before or after buying: sizes, materials, stock, compatibility, care, assembly, how to use it. |
| `account` | Login, passwords, two-step codes, changing the account email, deleting an account or personal data, newsletter and marketing emails, and account security. |
| `other` | Everything else: compliments, general feedback, sales pitches, partnership offers, job applications, spam, messages meant for someone else. |

## When a ticket could go to two queues

Apply these in order. The first rule that fits wins.

1. **Someone else used the account.** Orders the customer didn't place, a changed password they didn't change, or a login from somewhere strange: `account`.
2. **A refund is late after a return was accepted:** `billing`, whatever was wrong with the item.
3. **The item arrived damaged, broken, defective or wrong:** `returns`, even if the customer asks for a refund.
4. **Cancel or change an order.** If it has not shipped: `order_changes`. If it has shipped: a cancellation is `returns`, an address change is `shipping`. If the customer doesn't say and you can't tell: `order_changes`.
5. **Several problems in one ticket:** route by the problem with the highest urgency. If two are equally urgent, route by the first one mentioned.
6. **A product question that mentions an order** (for example "will the lamp I ordered work with dimmer switches?"): `product`.

## Urgency

| Urgency | When |
|---|---|
| `urgent` | A safety risk (something overheated, sparked, smoked, broke while in use, or hurt someone); fraud or someone else using the account; a threat of legal action or a chargeback. |
| `high` | Money taken wrongly (double charge, charged for a cancelled order); an order past its promised delivery date; a parcel marked delivered that never arrived; a stated deadline in the next 7 days (a move, a gift, an event). |
| `normal` | Everything else. |

## Order id

- Store order ids look like `ORD-48213`: the letters ORD, a hyphen, five digits.
- Customers write them many ways: `order 48213`, `#48213`, `ORD48213`, `ord-48213`, `order no. 48213`. Always return the normal form, `ORD-48213`.
- Tracking numbers, return references (like `RMA-30418`), invoice numbers, product codes, phone numbers, postcodes and prices are not order ids.
- If there is more than one order id, return the first one. If there is none, return `null`.

## Wants a refund

`true` only when the customer asks for their money back in some form: a refund, money back, reimbursement, reversing a charge, or a chargeback. Asking for an exchange, a replacement, store credit or a discount is `false`. Asking *about* the refund policy without asking for one is `false`. A refund that is late after a return is `true`.

## The output

```json
{"queue": "returns", "urgency": "normal", "order_id": "ORD-48213", "wants_refund": true}
```
