/**
 * Commerce resolvers (Query + Mutation): products, warehouses, label formats.
 */

const { queryProducts, saveProducts, removeProducts, queryWarehouses, saveWarehouses, removeWarehouses, queryLabelFormats, saveLabelFormats, removeLabelFormats } = require('../services/cn-commerce');

module.exports = {
  Query: {
    getProducts: (_, { input }, context) => queryProducts(context.prisma, context.identity, input),
    queryProducts: (_, { input }, context) => queryProducts(context.prisma, context.identity, input),
    getWarehouses: (_, { input }, context) => queryWarehouses(context.prisma, context.identity, input),
    queryWarehouses: (_, { input }, context) => queryWarehouses(context.prisma, context.identity, input),
    getLabelFormats: (_, { input }, context) => queryLabelFormats(context.prisma, context.identity, input),
    queryLabelFormats: (_, { input }, context) => queryLabelFormats(context.prisma, context.identity, input),
  },
  Mutation: {
    addProducts: (_, { input }, context) => saveProducts(context.prisma, context.identity, input),
    updateProducts: (_, { input }, context) => saveProducts(context.prisma, context.identity, input, true),
    removeProducts: (_, { ids }, context) => removeProducts(context.prisma, context.identity, ids),
    addWarehouses: (_, { input }, context) => saveWarehouses(context.prisma, context.identity, input),
    updateWarehouses: (_, { input }, context) => saveWarehouses(context.prisma, context.identity, input, true),
    removeWarehouses: (_, { ids }, context) => removeWarehouses(context.prisma, context.identity, ids),
    addLabelFormats: (_, { input }, context) => saveLabelFormats(context.prisma, context.identity, input),
    updateLabelFormats: (_, { input }, context) => saveLabelFormats(context.prisma, context.identity, input, true),
    removeLabelFormats: (_, { ids }, context) => removeLabelFormats(context.prisma, context.identity, ids),
  },
};