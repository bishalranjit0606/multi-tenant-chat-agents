import json

seed = json.loads(r"""
{
  "bookingPolicy": {
    "orgId": "org_b",
    "cancelFreeHours": 12,
    "lateFeeRate": 0.5,
    "document": "Policies",
    "section": "Cancellation"
  },
  "products": [
    {
      "sku": "TEA-JAS-50",
      "orgId": "org_a",
      "name": "Jasmine Green 50g",
      "category": "green",
      "price": 450,
      "stock": 20
    },
    {
      "sku": "TEA-ILAM-100",
      "orgId": "org_a",
      "name": "Ilam Gold 100g",
      "category": "black",
      "price": 520,
      "stock": 1
    },
    {
      "sku": "TEA-MASALA-100",
      "orgId": "org_a",
      "name": "Masala Chai 100g",
      "category": "black",
      "price": 380,
      "stock": 15
    },
    {
      "sku": "TEA-OOLONG-50",
      "orgId": "org_a",
      "name": "Himalayan Oolong 50g",
      "category": "oolong",
      "price": 640,
      "stock": 8
    },
    {
      "sku": "TEA-WHITE-30",
      "orgId": "org_a",
      "name": "White Peony 30g",
      "category": "white",
      "price": 720,
      "stock": 6
    },
    {
      "sku": "TEA-MINT-40",
      "orgId": "org_a",
      "name": "Mint Tulsi 40g",
      "category": "herbal",
      "price": 300,
      "stock": 18
    },
    {
      "sku": "TEA-GINGER-40",
      "orgId": "org_a",
      "name": "Ginger Lemon 40g",
      "category": "herbal",
      "price": 320,
      "stock": 14
    },
    {
      "sku": "TEA-EARL-100",
      "orgId": "org_a",
      "name": "Earl Grey 100g",
      "category": "black",
      "price": 410,
      "stock": 22
    },
    {
      "sku": "TEA-ENG-100",
      "orgId": "org_a",
      "name": "English Breakfast 100g",
      "category": "black",
      "price": 390,
      "stock": 16
    },
    {
      "sku": "TEA-SILVER-30",
      "orgId": "org_a",
      "name": "Silver Tips 30g",
      "category": "white",
      "price": 890,
      "stock": 4
    },
    {
      "sku": "TEA-ROSE-40",
      "orgId": "org_a",
      "name": "Rose Green 40g",
      "category": "green",
      "price": 470,
      "stock": 9
    },
    {
      "sku": "TEA-CHAM-30",
      "orgId": "org_a",
      "name": "Chamomile 30g",
      "category": "herbal",
      "price": 350,
      "stock": 11
    },
    {
      "sku": "TEA-DARJ-100",
      "orgId": "org_a",
      "name": "Second Flush 100g",
      "category": "black",
      "price": 610,
      "stock": 7
    },
    {
      "sku": "TEA-PUERH-80",
      "orgId": "org_a",
      "name": "Pu-erh Cake 80g",
      "category": "dark",
      "price": 980,
      "stock": 5
    },
    {
      "sku": "TEA-MATCHA-30",
      "orgId": "org_a",
      "name": "Ceremonial Matcha 30g",
      "category": "green",
      "price": 1250,
      "stock": 3
    },
    {
      "sku": "WARE-CUP-1",
      "orgId": "org_a",
      "name": "Clay Cup",
      "category": "teaware",
      "price": 650,
      "stock": 12
    },
    {
      "sku": "WARE-POT-1",
      "orgId": "org_a",
      "name": "Iron Pot",
      "category": "teaware",
      "price": 2400,
      "stock": 4
    },
    {
      "sku": "WARE-STRAIN-1",
      "orgId": "org_a",
      "name": "Steel Strainer",
      "category": "teaware",
      "price": 280,
      "stock": 20
    },
    {
      "sku": "TEA-HONEY-50",
      "orgId": "org_a",
      "name": "Honey Black 50g",
      "category": "black",
      "price": 430,
      "stock": 10
    },
    {
      "sku": "TEA-SMOKE-50",
      "orgId": "org_a",
      "name": "Smoked Lapsang 50g",
      "category": "black",
      "price": 560,
      "stock": 8
    }
  ],
  "customers": [
    {
      "id": "a_nima",
      "orgId": "org_a",
      "name": "Nima",
      "address": "Thamel, Kathmandu"
    },
    {
      "id": "a_sita",
      "orgId": "org_a",
      "name": "Sita",
      "address": "Patan, Lalitpur"
    },
    {
      "id": "a_ram",
      "orgId": "org_a",
      "name": "Ram",
      "address": "Bhaktapur"
    },
    {
      "id": "b_maya",
      "orgId": "org_b",
      "name": "Maya",
      "address": "Lazimpat, Kathmandu"
    },
    {
      "id": "b_arun",
      "orgId": "org_b",
      "name": "Arun",
      "address": "Jhamsikhel, Lalitpur"
    },
    {
      "id": "b_lina",
      "orgId": "org_b",
      "name": "Lina",
      "address": "Pokhara"
    }
  ],
  "orders": [
    {
      "id": "ord_nima_old",
      "orgId": "org_a",
      "customerId": "a_nima",
      "status": "delivered",
      "items": [
        {
          "sku": "TEA-MASALA-100",
          "name": "Masala Chai 100g",
          "qty": 1,
          "unitPrice": 380,
          "lineTotal": 380
        }
      ],
      "total": 380,
      "address": "Thamel, Kathmandu",
      "payment": "cash_on_delivery",
      "stockHeld": false,
      "history": [
        {
          "status": "delivered",
          "at": "2026-08-02T04:15:00.000Z"
        }
      ],
      "createdAt": "2026-08-01T04:15:00.000Z"
    },
    {
      "id": "ord_nima_last",
      "orgId": "org_a",
      "customerId": "a_nima",
      "status": "delivered",
      "items": [
        {
          "sku": "TEA-ILAM-100",
          "name": "Ilam Gold 100g",
          "qty": 2,
          "unitPrice": 480,
          "lineTotal": 960
        }
      ],
      "total": 960,
      "address": "Thamel, Kathmandu",
      "payment": "cash_on_delivery",
      "stockHeld": false,
      "history": [
        {
          "status": "delivered",
          "at": "2026-10-21T04:15:00.000Z"
        }
      ],
      "createdAt": "2026-10-20T04:15:00.000Z"
    },
    {
      "id": "ord_sita_1",
      "orgId": "org_a",
      "customerId": "a_sita",
      "status": "delivered",
      "items": [
        {
          "sku": "TEA-JAS-50",
          "name": "Jasmine Green 50g",
          "qty": 1,
          "unitPrice": 400,
          "lineTotal": 400
        }
      ],
      "total": 400,
      "address": "Patan, Lalitpur",
      "payment": "cash_on_delivery",
      "stockHeld": false,
      "history": [
        {
          "status": "delivered",
          "at": "2026-09-02T04:15:00.000Z"
        }
      ],
      "createdAt": "2026-09-01T04:15:00.000Z"
    }
  ],
  "services": [
    {
      "id": "svc_swedish",
      "orgId": "org_b",
      "name": "Swedish massage",
      "durationMin": 60,
      "price": 2500
    },
    {
      "id": "svc_deep",
      "orgId": "org_b",
      "name": "Deep tissue massage",
      "durationMin": 60,
      "price": 3000
    },
    {
      "id": "svc_physio",
      "orgId": "org_b",
      "name": "Physiotherapy session",
      "durationMin": 45,
      "price": 2200
    },
    {
      "id": "svc_yoga",
      "orgId": "org_b",
      "name": "Yoga group class",
      "durationMin": 60,
      "price": 800
    },
    {
      "id": "svc_prenatal",
      "orgId": "org_b",
      "name": "Prenatal massage",
      "durationMin": 60,
      "price": 2800
    },
    {
      "id": "svc_stretch",
      "orgId": "org_b",
      "name": "Stretch therapy",
      "durationMin": 30,
      "price": 1500
    }
  ],
  "practitioners": [
    {
      "id": "p_anita",
      "orgId": "org_b",
      "name": "Anita"
    },
    {
      "id": "p_binod",
      "orgId": "org_b",
      "name": "Binod"
    },
    {
      "id": "p_chhaya",
      "orgId": "org_b",
      "name": "Chhaya"
    }
  ],
  "hours": [
    {
      "orgId": "org_b",
      "weekday": "Sun",
      "open": "09:00",
      "close": "18:00"
    },
    {
      "orgId": "org_b",
      "weekday": "Mon",
      "open": "09:00",
      "close": "18:00"
    },
    {
      "orgId": "org_b",
      "weekday": "Tue",
      "open": "09:00",
      "close": "18:00"
    },
    {
      "orgId": "org_b",
      "weekday": "Wed",
      "open": "09:00",
      "close": "18:00"
    },
    {
      "orgId": "org_b",
      "weekday": "Thu",
      "open": "09:00",
      "close": "18:00"
    },
    {
      "orgId": "org_b",
      "weekday": "Fri",
      "open": "09:00",
      "close": "18:00"
    },
    {
      "orgId": "org_b",
      "weekday": "Sat",
      "open": "10:00",
      "close": "16:00"
    }
  ],
  "holidays": [
    {
      "orgId": "org_b",
      "date": "2026-11-08",
      "name": "Studio holiday"
    }
  ],
  "bookings": [
    {
      "id": "book_maya_past",
      "orgId": "org_b",
      "customerId": "b_maya",
      "serviceId": "svc_swedish",
      "practitionerId": "p_anita",
      "start": "2026-09-08T04:15:00.000Z",
      "end": "2026-09-08T05:15:00.000Z",
      "price": 2500,
      "status": "booked"
    },
    {
      "id": "book_arun_past",
      "orgId": "org_b",
      "customerId": "b_arun",
      "serviceId": "svc_yoga",
      "practitionerId": "p_binod",
      "start": "2026-09-10T04:15:00.000Z",
      "end": "2026-09-10T05:15:00.000Z",
      "price": 800,
      "status": "booked"
    }
  ],
  "knowledge": [
    {
      "orgId": "org_a",
      "document": "About",
      "section": "Who we are",
      "text": "Himali Tea House packs small-batch tea from Ilam and the hills around Nepal."
    },
    {
      "orgId": "org_a",
      "document": "About",
      "section": "Where we pack",
      "text": "Orders are packed in Kathmandu and sent from the Thamel workshop."
    },
    {
      "orgId": "org_a",
      "document": "Shipping",
      "section": "Delivery time",
      "text": "Inside Kathmandu, tea arrives in 2 to 4 days. Outside the valley, allow up to 7 days."
    },
    {
      "orgId": "org_a",
      "document": "Shipping",
      "section": "Delivery fee",
      "text": "Delivery is free above NPR 1500. Below that, the fee is NPR 120 inside the valley."
    },
    {
      "orgId": "org_a",
      "document": "Shipping",
      "section": "Cash on delivery",
      "text": "You can pay cash on delivery. The rider collects the order total at the door."
    },
    {
      "orgId": "org_a",
      "document": "Returns",
      "section": "Window",
      "text": "Unopened tea can be returned within 7 days of delivery."
    },
    {
      "orgId": "org_a",
      "document": "Returns",
      "section": "Opened tea",
      "text": "Opened tea leaves cannot be returned, unless the pack arrived damaged."
    },
    {
      "orgId": "org_a",
      "document": "Returns",
      "section": "Damaged parcel",
      "text": "If the parcel is damaged, write to us within 2 days with a photo."
    },
    {
      "orgId": "org_a",
      "document": "Brewing",
      "section": "Green tea",
      "text": "Steep green tea at 80C for 2 minutes. Do not use boiling water."
    },
    {
      "orgId": "org_a",
      "document": "Brewing",
      "section": "Black tea",
      "text": "Steep black tea at 95C for 3 to 4 minutes."
    },
    {
      "orgId": "org_a",
      "document": "Brewing",
      "section": "Matcha",
      "text": "Sift matcha, add 70C water, and whisk until the surface is foamy."
    },
    {
      "orgId": "org_a",
      "document": "FAQ",
      "section": "Storage",
      "text": "Keep tea in a closed tin, away from sunlight and strong smells."
    },
    {
      "orgId": "org_a",
      "document": "FAQ",
      "section": "Caffeine",
      "text": "Black tea has more caffeine than green tea. Herbal blends have none."
    },
    {
      "orgId": "org_a",
      "document": "FAQ",
      "section": "Gifts",
      "text": "Ask in the chat for a gift note. We print a short card and put it in the box."
    },
    {
      "orgId": "org_a",
      "document": "FAQ",
      "section": "Wholesale",
      "text": "Wholesale tins start at 20 packs. Ask the chat for the wholesale list."
    },
    {
      "orgId": "org_a",
      "document": "FAQ",
      "section": "Shelf life",
      "text": "Most sealed packs stay fresh for 12 months. Matcha is best within 3 months of opening."
    },
    {
      "orgId": "org_a",
      "document": "FAQ",
      "section": "Allergens",
      "text": "Plain leaf tea has no nuts. Flavoured blends list allergens on the tin label."
    },
    {
      "orgId": "org_a",
      "document": "FAQ",
      "section": "Organic",
      "text": "Ilam green and black lines are certified organic. Look for the organic mark on the pack."
    },
    {
      "orgId": "org_a",
      "document": "FAQ",
      "section": "Reorder",
      "text": "Say same as last time in chat to reorder. We re-check stock and the current price first."
    },
    {
      "orgId": "org_a",
      "document": "FAQ",
      "section": "Minimum order",
      "text": "There is no minimum for retail. Wholesale starts at 20 packs of one SKU."
    },
    {
      "orgId": "org_a",
      "document": "FAQ",
      "section": "Track order",
      "text": "Ask the chat for your order id. Pending orders can still be edited or cancelled."
    },
    {
      "orgId": "org_a",
      "document": "FAQ",
      "section": "Payment methods",
      "text": "We take cash on delivery. Card payment at the door is not available yet."
    },
    {
      "orgId": "org_a",
      "document": "FAQ",
      "section": "Sample packs",
      "text": "Sample tins are 15g. They use the same leaf as the full pack."
    },
    {
      "orgId": "org_a",
      "document": "FAQ",
      "section": "Water temperature",
      "text": "Use cooler water for green tea. Boiling water can make green tea bitter."
    },
    {
      "orgId": "org_a",
      "document": "FAQ",
      "section": "Loose leaf vs bags",
      "text": "We sell loose leaf and matcha. We do not sell paper tea bags."
    },
    {
      "orgId": "org_a",
      "document": "FAQ",
      "section": "Same day delivery",
      "text": "Same day delivery inside Kathmandu is only for orders placed before 11:00."
    },
    {
      "orgId": "org_b",
      "document": "About",
      "section": "The studio",
      "text": "Lotus Wellness Studio offers massage, physiotherapy, and yoga."
    },
    {
      "orgId": "org_b",
      "document": "About",
      "section": "Where we are",
      "text": "The studio is in Lazimpat, Kathmandu. The time zone is Asia/Kathmandu."
    },
    {
      "orgId": "org_b",
      "document": "Services",
      "section": "Massage",
      "text": "Swedish, deep tissue, and prenatal massage are one to one on a table."
    },
    {
      "orgId": "org_b",
      "document": "Services",
      "section": "Physiotherapy",
      "text": "Physiotherapy sessions assess pain and give a short home plan."
    },
    {
      "orgId": "org_b",
      "document": "Services",
      "section": "Yoga",
      "text": "Yoga group class is a shared hour. Bring your own mat if you have one."
    },
    {
      "orgId": "org_b",
      "document": "Practitioners",
      "section": "Anita",
      "text": "Anita leads Swedish massage and prenatal massage."
    },
    {
      "orgId": "org_b",
      "document": "Practitioners",
      "section": "Binod",
      "text": "Binod leads physiotherapy and yoga."
    },
    {
      "orgId": "org_b",
      "document": "Practitioners",
      "section": "Chhaya",
      "text": "Chhaya leads deep tissue massage and stretch therapy."
    },
    {
      "orgId": "org_b",
      "document": "Policies",
      "section": "Cancellation",
      "text": "Cancel at least 12 hours before the start for no fee. A later cancel keeps 50 percent of the price."
    },
    {
      "orgId": "org_b",
      "document": "Policies",
      "section": "Late arrival",
      "text": "If you are more than 15 minutes late, the session still ends at the booked time."
    },
    {
      "orgId": "org_b",
      "document": "Policies",
      "section": "What to wear",
      "text": "Wear loose clothes for yoga and physio. Massage clients are covered with a sheet."
    },
    {
      "orgId": "org_b",
      "document": "FAQ",
      "section": "First visit",
      "text": "Arrive 10 minutes early on your first visit so we can note your health history."
    },
    {
      "orgId": "org_b",
      "document": "FAQ",
      "section": "Parking",
      "text": "Bikes can park in the lane. Cars should use the public lot one block north."
    },
    {
      "orgId": "org_b",
      "document": "FAQ",
      "section": "Age",
      "text": "Yoga is for ages 16 and up. Massage for minors needs a guardian in the room."
    },
    {
      "orgId": "org_b",
      "document": "FAQ",
      "section": "Gift cards",
      "text": "Gift cards are sold at the desk. The chat can book a time, not sell a card."
    },
    {
      "orgId": "org_b",
      "document": "FAQ",
      "section": "How to book",
      "text": "Log in on the studio chat and ask for a service and time. The agent confirms before booking."
    },
    {
      "orgId": "org_b",
      "document": "FAQ",
      "section": "Reschedule",
      "text": "You can reschedule if the new slot is free. A conflicting move is refused with nearby options."
    },
    {
      "orgId": "org_b",
      "document": "FAQ",
      "section": "Time zone",
      "text": "All times are Asia/Kathmandu. Next Tuesday afternoon means 14:00 there."
    },
    {
      "orgId": "org_b",
      "document": "FAQ",
      "section": "Group yoga size",
      "text": "Yoga group class holds up to 12 people. Arrive early to keep your mat space."
    },
    {
      "orgId": "org_b",
      "document": "FAQ",
      "section": "Physio home plan",
      "text": "Each physiotherapy visit includes a short home plan you can follow between sessions."
    },
    {
      "orgId": "org_b",
      "document": "FAQ",
      "section": "Prenatal massage",
      "text": "Prenatal massage needs a clear second trimester note. Anita leads those sessions."
    },
    {
      "orgId": "org_b",
      "document": "FAQ",
      "section": "Deep tissue aftercare",
      "text": "Drink water after deep tissue work. Mild soreness for one day is normal."
    },
    {
      "orgId": "org_b",
      "document": "FAQ",
      "section": "Packages",
      "text": "Four-session packages are sold at the desk. The chat books single visits."
    },
    {
      "orgId": "org_b",
      "document": "FAQ",
      "section": "Illness",
      "text": "Stay home if you have a fever. Message the chat to cancel under the studio policy."
    },
    {
      "orgId": "org_b",
      "document": "FAQ",
      "section": "Gender preference",
      "text": "You can ask for a practitioner by name. Availability still depends on open slots."
    },
    {
      "orgId": "org_b",
      "document": "FAQ",
      "section": "Payment at studio",
      "text": "Pay at the desk after the session. Cash and local cards are accepted there."
    }
  ]
}
""")
