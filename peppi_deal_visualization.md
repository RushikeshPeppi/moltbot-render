# Peppi B2B Dropshipping: Deal Visualization

This visualization captures the business model and deal lifecycle for **Peppi**, a B2B office supply dropshipping startup targeting SMBs in New York.

## Mermaid Diagram (Excalidraw Compatible)

```mermaid
graph TD
    %% Core Entities
    SMB[Target: SMBs 10-100 employees]
    CO[Pilot: Co-working Space 15 companies]
    PE[Peppi SMS Platform]
    WH[Local NY Warehouse]
    SUP[China Wholesale Suppliers]

    %% Lifecycle
    SMB -->|Order via SMS| PE
    CO -->|Pilot Orders| PE
    PE -->|Payment: Upfront first 3 orders / Net 15| PE
    PE -->|Order Fulfillment| WH
    SUP -->|40-50% Cheaper Stock| WH
    WH -->|Next-Day Delivery| SMB

    %% Key Values
    subgraph "Economics & Strategy"
        M1[30% Markup - Small Orders]
        M2[20% Markup - Bulk Orders]
        S1[Subscription Model - Paper/Pens]
        P[Target Profit: $100-150 / order]
    end

    subgraph "Operational Edge"
        E1[Cheaper than Staples/Uline]
        E2[No Inventory Management for SMB]
        E3[SMS Lower Friction]
    end

    %% Styling
    style SMB fill:#f9f,stroke:#333,stroke-width:2px
    style PE fill:#bbf,stroke:#333,stroke-width:2px
    style SUP fill:#bfb,stroke:#333,stroke-width:2px
    style P fill:#fbb,stroke:#333,stroke-width:4px
```

## Business Deal Summary
- **Average Order Value**: $500 - $800.
- **Net Profit**: $100 - $150 per order.
- **Revenue Model**: Tiered markups + Subscription revenue for recurring supplies.
- **Growth Strategy**: Pilot with co-working spaces, then scale through direct outreach to office managers.
