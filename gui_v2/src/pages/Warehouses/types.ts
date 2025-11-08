export interface Warehouse {
  id: string;
  name: string;
  city: string;
  state: string;
  contactFirstName: string;
  contactLastName: string;
  phone: string;
  email: string;
  messagingPlatform?: string;
  messagingId?: string;
  address1: string;
  address2?: string;
  addressCity: string;
  addressState: string;
  addressZip: string;
  costDescription: string;
}
