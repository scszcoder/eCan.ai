'use strict';

const ACCOUNT_COLUMNS = [
  'user_name', 'subid', 'dob', 'email', 'phone', 'addr', 'ssn4', 'sign_on_date',
  'last_actions', 'pay_method1', 'pay1_details', 'pay_method2', 'pay2_details',
  'pay_method3', 'pay3_details', 'subs', 'fund', 'quota', 'states',
];

function number(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function text(value) {
  return value == null ? '' : String(value);
}

function accountValues(item, owner) {
  return [
    owner, text(item.subid), text(item.dob), text(item.email), text(item.phone), text(item.addr),
    text(item.ssn4), text(item.sign_on_date), JSON.stringify(item.last_actions || {}),
    text(item.pay_method1), text(item.pay1_details), text(item.pay_method2), text(item.pay2_details),
    text(item.pay_method3), text(item.pay3_details), text(item.subs), number(item.fund),
    number(item.quota), text(item.states),
  ];
}

function accountRow(row) {
  return {
    ...row,
    actid: String(row.actid),
    fund: number(row.fund),
    quota: number(row.quota),
    last_actions: row.last_actions || {},
  };
}

function orderRow(row) {
  return {
    ...row,
    BID: String(row.bid),
    actid: String(row.actid),
    orderID: row.orderid,
    discountType: row.discounttype,
    dealType: row.dealtype,
    unitPrice: number(row.unitprice),
    payMethod: row.paymethod,
    beginDate: row.begindate instanceof Date ? row.begindate.toISOString() : row.begindate,
    endDate: row.enddate instanceof Date ? row.enddate.toISOString() : row.enddate,
  };
}

function query(prisma, statement, values = []) {
  return prisma.$queryRawUnsafe(statement, ...values);
}

async function saveAccounts(prisma, identity, input) {
  const results = [];
  for (const item of input || []) {
    try {
      const actid = number(item.actid);
      if (actid > 0) {
        const rows = await query(prisma,
          `UPDATE accounts SET subid=$1, dob=$2, email=$3, phone=$4, addr=$5, ssn4=$6,
           sign_on_date=$7, last_actions=$8::jsonb, pay_method1=$9, pay1_details=$10,
           pay_method2=$11, pay2_details=$12, pay_method3=$13, pay3_details=$14, subs=$15,
           fund=$16, quota=$17, states=$18 WHERE actid=$19 AND user_name=$20 RETURNING *`,
          [...accountValues(item, identity.sub).slice(1), actid, identity.sub]);
        if (!rows.length) throw new Error('Account not found');
        results.push({ id: String(rows[0].actid), success: true });
      } else {
        const rows = await query(prisma,
          `INSERT INTO accounts (${ACCOUNT_COLUMNS.join(', ')})
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9::jsonb,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19)
           RETURNING *`,
          accountValues(item, identity.sub));
        results.push({ id: String(rows[0].actid), success: true });
      }
    } catch (error) {
      results.push({ id: item?.actid == null ? null : String(item.actid), success: false, error: error.message });
    }
  }
  return JSON.stringify(results);
}

async function queryAccounts(prisma, identity, ops) {
  const actid = number(ops?.[0]?.actid);
  const rows = actid > 0
    ? await query(prisma, 'SELECT * FROM accounts WHERE actid=$1 AND user_name=$2', [actid, identity.sub])
    : await query(prisma, 'SELECT * FROM accounts WHERE user_name=$1 ORDER BY actid DESC LIMIT 200', [identity.sub]);
  return JSON.stringify(rows.map(accountRow));
}

async function queryMine(prisma, identity) {
  const accounts = await query(prisma, 'SELECT * FROM accounts WHERE user_name=$1 ORDER BY actid DESC', [identity.sub]);
  if (!accounts.length) return { acctInfo: null, ordersInfo: [] };
  const accountIds = accounts.map((account) => BigInt(account.actid));
  const orders = await query(prisma,
    'SELECT * FROM cnbus WHERE actid = ANY($1::bigint[]) ORDER BY bid DESC', [accountIds]);
  return { acctInfo: accountRow(accounts[0]), ordersInfo: orders.map(orderRow) };
}

module.exports = { queryAccounts, queryMine, saveAccounts };