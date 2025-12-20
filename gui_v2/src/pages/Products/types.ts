export interface ProductInventory {
  location: string;
  quantity: string;
}

export interface ProductDropShipper {
  name: string;
  quantity: string;
}

export interface ProductMedia {
  url: string;
  description: string;
}

export interface ProductSupplier {
  name: string;
  link: string;
  factoryUnitPrice: number | string;
}

export interface ProductPlatform {
  name: string;
  link: string;
  id: string;
}

export interface Product {
  id: string;
  nickName: string;
  title: string;
  features: string;
  sizeL: string;
  sizeW: string;
  sizeH: string;
  weightOz: string;
  fragile: boolean;
  batteryInside: boolean;
  chemical: boolean;
  flammable: boolean;
  city?: string; // for list display
  state?: string; // for list display
  inventories: ProductInventory[];
  dropShippers: ProductDropShipper[];
  media: ProductMedia[];
  suppliers: ProductSupplier[];
  platforms: ProductPlatform[];
}
