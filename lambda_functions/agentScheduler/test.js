

var test_resp1 = [[{ "header": {  "name": "browse_search_kw",  "os": "win",  "version": "1.0", "author": "AIPPS LLC", "skid": "PUBWINADSWIN0000001", "description": "Buying skill on amazon with ADSPower for Windows." }}]];

var test_resp_string = JSON.stringify(test_resp1);

const test_add_bots_resp = [
        {
            "bid": 7,
            "owner": "abc@cde.com",
            "levels": "undefined",
            "levelStart": "amz:2023-01-14,ebay:2023-01-14,etsy:2023-01-14",
            "gender": "Male",
            "birthday": "1998-01-01",
            "interests": "amz:any:any,Clothing_Shoes_Jewelry_Watches,Pet_Supplies,Outdoors,Sports",
            "location": "TX",
            "roles": "amz:buyer,ebay:buyer,etsy:buyer",
            "status": "Enabled",
            "delDate": "2523-01-14"
        },
        {
            "bid": 8,
            "owner": "abc@cde.com",
            "levels": "undefined",
            "levelStart": "amz:2023-01-14,ebay:2023-01-14",
            "gender": "Male",
            "birthday": "1998-01-01",
            "interests": "amz:any:any,Clothing_Shoes_Jewelry_Watches,Pet_Supplies,Outdoors,Sports,ebay:any:any",
            "location": "CA",
            "roles": "amz:buyer,ebay:buyer",
            "status": "Enabled",
            "delDate": "3023-01-14"
        },
        {
            "bid": 9,
            "owner": "abc@cde.com",
            "levels": "undefined",
            "levelStart": "amz:2023-01-14,amz:2023-01-14",
            "gender": "Male",
            "birthday": "199-01-01",
            "interests": "amz:any:any,Clothing_Shoes_Jewelry_Watches,Pet_Supplies,Outdoors,Sports,ebay:any:any,etsy:any:any",
            "location": "NY",
            "roles": "amz:buyer,amz:seller",
            "status": "Enabled",
            "delDate": "3523-01-14"
        }
    ];

const test_add_missions_resp = [];

const test_add_skills_resp = [];


const test_get_schedule_resp = [];

var  testcases = [
    {
        "name" : "unit test",
        "skip" : false,
        "number" : "0",
        "function" : "reverseString",
        "arguments" : ["abcd4fg"],
        "expected" : "gf4dcba",
    }
];

// check whether date1 is within n days from date2:  (date1, date2, n)
testcases.push(
    {
        "name" : "unit test",
        "skip" : true,
        "number" : "5",
        "function" : "withinDays",
        "arguments" : [new Date("2023-01-01"), new Date(), 24],
        "expected" : true
    }
);

// check whether a bot is fit to execute a mission, the result is a score, the higher the score, the better fit is for this bot.
testcases.push(
    {
        "name" : "unit test",
        "skip" : true,
        "number" : "10",
        "function" : "botFitsMission",
        "arguments" : [
            {
                "bid" : 0,
                "owner" : "",
                "levels" : "",
                "levelStart" : "",
                "gender" : "",
                "birthday" : "",
                "interests" : "",
                "location" : "",
                "roles" : "",
                "status" : "",
                "delDate" : ""
            }, 
            {
                "mid": "1",
                "owner": "songc@yahoo.com",
                "botid": "3",
                "cuspas": "win,adspow,amz",
                "search_kw": "yoga suit",
                "search_cat": "Sports",
                "status": "",
                "repeat": "0",
                "store": "peach",
                "asin": "0012345",
                "brand": "peach",
                "mtype": "buy"
            }, 
            {"testmode": false, 'skip_botFitsMission': false, 'botFitsMission' : null}
            ],
        "expected" : 10
    }
);

// get the next available date on this mission and this bot, decision needs input of historical mission data too....
// (bot, newMission, pastMissions)
testcases.push(
    {
        "name" : "unit test",
        "skip" : true,
        "number" : "15",
        "function" : "getNextAvailableDate",
        "arguments" : [
             {
                "botid" : 0,
                "birthday" : ""
            }, 
            {
                "mid": "1",
                "owner": "songc@yahoo.com",
                "botid": "3",
                "cuspas": "win,adspow,amz",
                "search_kw": "yoga suit",
                "search_cat": "Sports",
                "status": "",
                "repeat": "0",
                "store": "peach",
                "asin": "0012345",
                "brand": "peach",
                "mtype": "buy"
            }, 
             {
                "bid" : 0,
                "owner" : "",
                "levels" : "",
                "levelStart" : "",
                "gender" : "",
                "birthday" : "",
                "interests" : "",
                "location" : "",
                "roles" : "",
                "status" : "",
                "delDate" : ""
            }, 
            [{
                "mid": "1",
                "owner": "songc@yahoo.com",
                "botid": "3",
                "cuspas": "win,adspow,amz",
                "search_kw": "yoga suit",
                "search_cat": "Sports",
                "status": "",
                "repeat": "0",
                "store": "peach",
                "asin": "0012345",
                "brand": "peach",
                "mtype": "buy"
            }, 
            ]
        ],
        "expected" : new Date("2023-01-01")
    }
);

// should re-arrange missions based on mission types
// inut: a list of missions.
// output: a group of list of missions base on mission types.
// possible types: "walk_routine", "walk_completion", "browse", "buy", "goodFB", "badFB", "sell"
testcases.push(
    {
        "name" : "unit test",
        "skip" : true,
        "number" : "20",
        "function" : "reArrangeMissions",
        "arguments" : [[{
                "mid": "1",
                "owner": "songc@yahoo.com",
                "botid": "3",
                "cuspas": "win,adspow,amz",
                "search_kw": "yoga suit",
                "search_cat": "Sports",
                "status": "",
                "repeat": "0",
                "store": "peach",
                "asin": "0012345",
                "brand": "peach",
                "mtype": "buy"
            },
            {
                "mid": "1",
                "owner": "songc@yahoo.com",
                "botid": "3",
                "cuspas": "win,adspow,amz",
                "search_kw": "yoga suit",
                "search_cat": "Sports",
                "status": "",
                "repeat": "0",
                "store": "peach",
                "asin": "0012345",
                "brand": "peach",
                "mtype": "walk_routine"
            }]],
        "expected" : [[{
                "mid": "1",
                "owner": "songc@yahoo.com",
                "botid": "3",
                "cuspas": "win,adspow,amz",
                "search_kw": "yoga suit",
                "search_cat": "Sports",
                "status": "",
                "repeat": "0",
                "store": "peach",
                "asin": "0012345",
                "brand": "peach",
                "mtype": "walk_routine"
            }],
            [{
                "mid": "1",
                "owner": "songc@yahoo.com",
                "botid": "3",
                "cuspas": "win,adspow,amz",
                "search_kw": "yoga suit",
                "search_cat": "Sports",
                "status": "",
                "repeat": "0",
                "store": "peach",
                "asin": "0012345",
                "brand": "peach",
                "mtype": "buy"
            }]]
    }
);

// get issions by Ids from the database.
testcases.push(
    {
        "name" : "unit test",
        "skip" : true,
        "number" : "25",
        "function" : "getMissionsByIds",
        "arguments" : [new Date("2023-01-01"), new Date(), 24],
        "expected" : true
    }
);

// get bots by Ids from the database.
testcases.push(
    {
        "name" : "unit test",
        "skip" : true,
        "number" : "30",
        "function" : "getBotsByIds",
        "arguments" : [new Date("2023-01-01"), new Date(), 24],
        "expected" : true
    }
);

// get bots by current owner from the database.
testcases.push(
    {
        "name" : "unit test",
        "skip" : true,
        "number" : "35",
        "function" : "getBots",
        "arguments" : [new Date("2023-01-01"), new Date(), 24],
        "expected" : true
    }
);


testcases.push(
    {
        "name" : "unit test",
        "skip" : true,
        "number" : "40",
        "function" : "getMissionsWithMissionIds",
        "arguments" : [new Date("2023-01-01"), new Date(), 24],
        "expected" : true
    }
);

//get missions by bot ids.
testcases.push(
    {
        "name" : "unit test",
        "skip" : true,
        "number" : "45",
        "function" : "getMissionsWithBotIds",
        "arguments" : [new Date("2023-01-01"), new Date(), 24],
        "expected" : true
    }
);

//get missions
testcases.push(
    {
        "name" : "unit test",
        "skip" : true,
        "number" : "50",
        "function" : "getMissions",
        "arguments" : [new Date("2023-01-01"), new Date(), 24],
        "expected" : true
    }
);

// try to assign missions to availabe bots.
// (owner, newMissions, myMissions, callback, logflag, test_stub)
// return newMissions with date fields filled with the schedule date....
// this is one of the core function. 
// here are different test cases:
// 1) add 1 buy mission - 
//      a) no bot of 2 bots found.
//          i) failed due to violation of same store buy
//          ii) failed due to violation of same item buy
//          iii) failed due to violation of # of goodFB in last 30 days
//          iv) failed due to violation of # of badFB in last 90 days
//          v) failed due to violation of # of same search buys in 6 months.
//          vi) failed due to violation of green bot last buy gap
//          vii) failed due to violation of initial green bot wait days.
//          viii) failed due to violation of max # of buys within last 30 days.
//          ix) failed due to violation of max buy to fb ratio.
//          x) failed due to violation of good to bad FB ratio.
//      b) 1 green bot of 2 bots found 
//          i) 1 regular bot of 2 bots found
//      c) 1 green bot of 3 bots found 
//          i) 1 regular bot of 3 bots found
//      d) 2 green bot of 3 bots found 
//          i) 1 green bot and 1 regular bot of 3 bots found
//          ii) 2 regular bot of 3 bots found
// 2) add 1 goodFB mission-
//      a) failed to find a bot
//          i) due to FB violation
//      b) find 1 green bot
//          i) find 1 regular bot.
// 3) add 1 badFB mission
// 4) add 1 sell mission
// 5) add 1 buy mission 1 sell mission
// 6) add 2 same buy missions - same items
// 7) add 2 different buy missions - same store, differnet items
// 8) add 2 different buy missions - different store, same type of products.
testcases.push(
    {
        "name" : "unit test",
        "skip" : false,
        "functype" : "asyn",
        "number" : "55",
        "function" : "assignMissions",
        "arguments" : [
            "songc@yahoo.com", 
            [
                {
                    mid : 0,
                    botid : 0,
                    ticket : "1",
                    owner : "abc@cde.com",
                    status : "COMPLETED",
                    type : "buy",
                    cuspas : "win,chrome,amz",
                    createon : "2023-01-30",
                    esttime : "1",
                    runtime : "",
                    trepeat : "once",
                    category  : "Sports",
                    phrase  : "yoga ball",
                    pseudoStore : "store0",
                    pseudoBrand : "brand0",
                    pseudoASIN : "12345",
                    esd : "2023-01-30",
                    ecd : "2023-01-31",
                    asd : "2023-01-30",
                    abd : "2023-01-30",
                    aad : "",
                    afd : "",
                    acd : "2023-01-31",
                    config  : "",
                    skills  : "win_chrome_amz_walk,win_chrome_amz_buy",
                    delDate  : ""
                },
                {
                    mid : 1,
                    botid : 1,
                    ticket : "2",
                    owner : "abc@cde.com",
                    status : "COMPLETED",
                    type : "buy",
                    cuspas : "win,chrome,amz",
                    createon : "2023-01-10",
                    esttime : "1",
                    runtime : "",
                    trepeat : "once",
                    category  : "Sports",
                    phrase  : "yoga ball",
                    pseudoStore : "store0",
                    pseudoBrand : "brand0",
                    pseudoASIN : "23456",
                    esd : "2023-01-24",
                    ecd : "2023-01-25",
                    asd : "2023-01-24",
                    abd : "2023-01-25",
                    aad : "",
                    afd : "",
                    acd : "2023-01-25",
                    config  : "",
                    skills  : "win_chrome_amz_walk,win_chrome_amz_buy",
                    delDate  : ""
                }
            ],
            [
                {
                    mid : 4,
                    botid : 0,
                    ticket : "3",
                    owner : "abc@cde.com",
                    status : "ASSIGNED",
                    type : "buy",
                    cuspas : "win,chrome,amz",
                    createon : "2023-01-30",
                    esttime : "1",
                    runtime : "",
                    trepeat : "once",
                    category  : "Sports",
                    phrase  : "yoga ball",
                    pseudoStore : "store1",
                    pseudoBrand : "brand1",
                    pseudoASIN : "56789",
                    esd : "2023-02-02 00:00:00",
                    ecd : "2023-02-02 00:00:00",
                    asd : "2023-02-02 00:00:00",
                    abd : "2023-02-02 00:00:00",
                    acd : "2023-02-02 00:00:00",
                    afd : "2023-02-02 00:00:00",
                    acd : "2023-02-02 00:00:00",
                    config  : "",
                    skills  : "win_chrome_amz_walk,win_chrome_amz_buy",
                    delDate  : ""
                },
                {
                    mid : 6,
                    botid : 1,
                    ticket : "4",
                    owner : "abc@cde.com",
                    status : "ASSIGNED",
                    type : "buy",
                    cuspas : "win,chrome,amz",
                    createon : "2023-01-30",
                    esttime : "1",
                    runtime : "",
                    trepeat : "once",
                    category  : "Sports",
                    phrase  : "dumb bell",
                    pseudoStore : "store1",
                    pseudoBrand : "brand1",
                    pseudoASIN : "67890",
                    esd : "2023-02-02 00:00:00",
                    ecd : "2023-02-02 00:00:00",
                    asd : "2023-02-02 00:00:00",
                    abd : "2023-02-02 00:00:00",
                    acd : "2023-02-02 00:00:00",
                    afd : "2023-02-02 00:00:00",
                    acd : "2023-02-02 00:00:00",
                    config  : "",
                    skills  : "win_chrome_amz_walk,win_chrome_amz_buy",
                    delDate  : ""
                },
                {
                    mid : 7,
                    botid : 0,
                    ticket : "5",
                    owner : "abc@cde.com",
                    status : "ASSIGNED",
                    type : "sell",
                    cuspas : "win,chrome,amz",
                    createon : "2023-01-30",
                    esttime : "10",
                    runtime : "",
                    trepeat : "daily",
                    category  : "",
                    phrase  : "",
                    pseudoStore : "",
                    pseudoBrand : "",
                    pseudoASIN : "",
                    esd : "",
                    ecd : "",
                    asd : "",
                    abd : "",
                    acd : "",
                    afd : "",
                    acd : "",
                    config  : "",
                    skills  : "win_chrome_ebay_sell, win_chrome_custom0_buy_label",
                    delDate  : ""
                }
            ],
            undefined, 
            undefined,
            {   "testmode": true,
                "skip_getBots" : true,
                "getBots" : undefined,
                "bots": [
                    {
                        bid : 0,
                        owner : "songc@yahoo.com",
                        gender : "male",
                        levels : "amz:green:buyer,ebay:normal:seller",
                        levelStart : "amz:buyer:green:2022-12-01,ebay:seller:normal:2022-12-01",
                        birthday : "2022-11-01 00:00:00",
                        location : "houston,tx",
                        roles : "amz:buyer,ebay:seller",
                        interests : "Electronics,Outdoors,Sports"
                    },
                    {
                        bid : 1,
                        owner : "songc@yahoo.com",
                        gender : "female",
                        levels : "amz:nomal:buyer",
                        levelStart : "amz:buyer:normal:2022-12-01",
                        birthday : "2022-10-01 00:00:00",
                        location : "Honolulu,hi",
                        roles : "amz:buyer",
                        interests : "Sports"
                    }
                ]
            }
        ],
        "expected" : true
    }
);

//calculate a date that n days after the indate.
//(n, indate)
// output: output date.
testcases.push(
    {
        "name" : "unit test",
        "skip" : false,
        "number" : "60",
        "function" : "nDaysAfter",
        "arguments" : [7, new Date("2023-01-25")],
        "expected" : new Date("2023-02-01")
    }
);

//calculate # of days between 2 different date
//(date1, date1)
// output: # of days.
testcases.push(
    {
        "name" : "unit test",
        "skip" : true,
        "number" : "65",
        "function" : "daysDiff",
        "arguments" : [new Date("2023-01-25"), new Date("2023-01-25")],
        "expected" : 0
    }
);

testcases.push(
    {
        "name" : "unit test",
        "skip" : true,
        "number" : "66",
        "function" : "daysDiff",
        "arguments" : [new Date("2023-02-01"), new Date("2023-01-24")],
        "expected" : 8
    }
);

// find out a bot's level given the mission.
// input: bot, missin, stub
// output: level
testcases.push(
    {
        "name" : "unit test",
        "skip" : true,
        "number" : "70",
        "function" : "getBotLevelGivenMission",
        "arguments" : [new Date("2023-01-01"), new Date(), 24],
        "expected" : true
    }
);

// try to schedule missions to run by bots.
//(bots, newMissions, allMissions, test_stub)
// return newMissions with dates fields updated.....
testcases.push(
    {
        "name" : "unit test",
        "skip" : true,
        "number" : "75",
        "function" : "scheduleMissions",
        "arguments" : [
            [
                {
                    bid : 0,
                    owner : "abc@cde.com",
                    gender : "male",
                    levels : "amz:green:buyer,ebay:normal:seller",
                    location : "houston,tx",
                    roles : "amz:buyer,ebay:seller",
                    interests : "Electronics,Outdoors,Sports"
                },
                {
                    bid : 1,
                    owner : "abc@cde.com",
                    gender : "female",
                    levels : "amz:nomal:buyer",
                    location : "Honolulu,hi",
                    roles : "amz:buyer",
                    interests : "Sports"
                },
            ], 
            [
                {
                    mid : 0,
                    botid : 0,
                    ticket : "1",
                    owner : "abc@cde.com",
                    status : "COMPLETED",
                    type : "buy",
                    cuspas : "win,chrome,amz",
                    createon : "2023-01-30",
                    esttime : "1",
                    runtime : "",
                    trepeat : "once",
                    category  : "Sports",
                    phrase  : "yoga ball",
                    pseudoStore : "store0",
                    pseudoBrand : "brand0",
                    pseudoASIN : "12345",
                    esd : "2023-01-30",
                    ecd : "2023-01-31",
                    asd : "2023-01-30",
                    abd : "2023-01-30",
                    aad : "",
                    afd : "",
                    acd : "2023-01-31",
                    config  : "",
                    skills  : "win_chrome_amz_walk,win_chrome_amz_buy",
                    delDate  : ""
                },
                {
                    mid : 1,
                    botid : 1,
                    ticket : "2",
                    owner : "abc@cde.com",
                    status : "COMPLETED",
                    type : "buy",
                    cuspas : "win,chrome,amz",
                    createon : "2023-01-10",
                    esttime : "1",
                    runtime : "",
                    trepeat : "once",
                    category  : "Sports",
                    phrase  : "yoga ball",
                    pseudoStore : "store0",
                    pseudoBrand : "brand0",
                    pseudoASIN : "23456",
                    esd : "2023-01-24",
                    ecd : "2023-01-25",
                    asd : "2023-01-24",
                    abd : "2023-01-25",
                    aad : "",
                    afd : "",
                    acd : "2023-01-25",
                    config  : "",
                    skills  : "win_chrome_amz_walk,win_chrome_amz_buy",
                    delDate  : ""
                }
            ],
            [
                {
                    mid : 4,
                    botid : 0,
                    ticket : "3",
                    owner : "abc@cde.com",
                    status : "ASSIGNED",
                    type : "buy",
                    cuspas : "win,chrome,amz",
                    createon : "2023-01-30",
                    esttime : "1",
                    runtime : "",
                    trepeat : "once",
                    category  : "Sports",
                    phrase  : "yoga ball",
                    pseudoStore : "store1",
                    pseudoBrand : "brand1",
                    pseudoASIN : "56789",
                    esd : "2023-02-02 00:00:00",
                    ecd : "2023-02-02 00:00:00",
                    asd : "2023-02-02 00:00:00",
                    abd : "2023-02-02 00:00:00",
                    acd : "2023-02-02 00:00:00",
                    afd : "2023-02-02 00:00:00",
                    acd : "2023-02-02 00:00:00",
                    config  : "",
                    skills  : "win_chrome_amz_walk,win_chrome_amz_buy",
                    delDate  : ""
                },
                {
                    mid : 6,
                    botid : 1,
                    ticket : "4",
                    owner : "abc@cde.com",
                    status : "ASSIGNED",
                    type : "buy",
                    cuspas : "win,chrome,amz",
                    createon : "2023-01-30",
                    esttime : "1",
                    runtime : "",
                    trepeat : "once",
                    category  : "Sports",
                    phrase  : "dumb bell",
                    pseudoStore : "store1",
                    pseudoBrand : "brand1",
                    pseudoASIN : "67890",
                    esd : "2023-02-02 00:00:00",
                    ecd : "2023-02-02 00:00:00",
                    asd : "2023-02-02 00:00:00",
                    abd : "2023-02-02 00:00:00",
                    acd : "2023-02-02 00:00:00",
                    afd : "2023-02-02 00:00:00",
                    acd : "2023-02-02 00:00:00",
                    config  : "",
                    skills  : "win_chrome_amz_walk,win_chrome_amz_buy",
                    delDate  : ""
                },
                {
                    mid : 7,
                    botid : 0,
                    ticket : "5",
                    owner : "abc@cde.com",
                    status : "ASSIGNED",
                    type : "sell",
                    cuspas : "win,chrome,amz",
                    createon : "2023-01-30",
                    esttime : "10",
                    runtime : "",
                    trepeat : "daily",
                    category  : "",
                    phrase  : "",
                    pseudoStore : "",
                    pseudoBrand : "",
                    pseudoASIN : "",
                    esd : "",
                    ecd : "",
                    asd : "",
                    abd : "",
                    acd : "",
                    afd : "",
                    acd : "",
                    config  : "",
                    skills  : "wi_chrome_ebay_sell, win_chrome_custom0_buy_label",
                    delDate  : ""
                }
            ], 
            {"testmode": false}
        ],
        "expected" : true
    }
);

// qualify regular bots.
// no need to test, never been used....
testcases.push(
    {
        "name" : "unit test",
        "skip" : true,
        "number" : "80",
        "function" : "regularQual",
        "arguments" : [new Date("2023-01-01"), new Date(), 24],
        "expected" : true
    }
);

//select category based on interests....
//input: (interests, n)
//output: n categories.
testcases.push(
    {
        "name" : "unit test",
        "skip" : true,
        "number" : "85",
        "function" : "selCategories",
        "arguments" : ["abc|bcd|cde,abc|bbd|ccd,aaa", 1],
        "expected" : [["abc", "bcd", "cde"]]
    }
);

//randomly pick an site entrance....
// input: (distraction: boolean)
// output: entrance.
testcases.push(
    {
        "name" : "unit test",
        "skip" : true,
        "number" : "90",
        "function" : "selEntrance",
        "arguments" : ["amz", true],
        "expected" : ["Search KW"]
    }
);
testcases.push(
    {
        "name" : "unit test",
        "skip" : true,
        "number" : "91",
        "function" : "selEntrance",
        "arguments" : ["amz", false],
        "expected" : ["Distraction"]
    }
);

//randomly select distraction type
// input: none.
// output: distraction type
testcases.push(
    {
        "name" : "unit test",
        "skip" : true,
        "number" : "95",
        "function" : "selDistraction",
        "arguments" : ["amz"],
        "expected" : "Lowest Price"
    }
);

// select search phrase
// input: (interests, n)
// output: n phrases.
testcases.push(
    {
        "name" : "unit test",
        "skip" : true,
        "number" : "100",
        "function" : "selSearchTerm",
        "arguments" : [new Date("2023-01-01"), new Date(), 24],
        "expected" : true
    }
);


//insert a mission action item into regular todo.
// input: todos, mission
// output: updated todos.
testcases.push(
    {
        "name" : "unit test",
        "skip" : true,
        "number" : "105",
        "function" : "insertMission",
        "arguments" : [new Date("2023-01-01"), new Date(), 24],
        "expected" : true
    }
);

// input: mission
// from misison's status, get one of the most recent action date.
testcases.push(
    {
        "name" : "unit test",
        "skip" : true,
        "number" : "110",
        "function" : "getMostRecentActionDate",
        "arguments" : [{type: "buy", status: "ASSIGNED", createon: "2022-12-02", asd: new Date("2023-01-01"), acd: "2023-01-02", abd: "", aad: "", afd: ""}],
        "expected" : "2022-12-02"
    }
);

// check to-be-dones on a bot:
// input: (bot, missions(owner all missions), test_stub)
//output: taskList
// a) no incomplete buys, no incomplete walk 
// b) 1 incomplete buy - new task generated./no new task genrated. 0 incomplete walk 
// c) 1 incomplete buys - 1 incomplete walk, 1 buyer role - 
// c) 1 incomplete buys - 1 incomplete walk, 2 site buyer roles - 

testcases.push(
    {
        "name" : "unit test",
        "skip" : true,
        "number" : "115",
        "function" : "checkTBDOnBot",
        "arguments" : [
            {
                bid: 1, 
                botid: 1, 
                owner: "", 
                roles: "", 
                interests:""
                
            }, 
            [
                {
                    mid : 0,
                    type: "buy",
                    botid: 1,
                    status: "Completed"
                }
            ], 
            {
                testmode: false
            }
        ],
        "expected" : true
    }
);

// generate work action items.. steps
//input: (bot, todos, missions, test_stub)
//output: 
// this function never used.... no need to test.
testcases.push(
    {
        "name" : "unit test",
        "skip" : true,
        "number" : "120",
        "function" : "genWorkActinItems",
        "arguments" : [new Date("2023-01-01"), new Date(), 24],
        "expected" : true
    }
);

//input: (bot, todos, missions, test_stub)
//output: aiList - action item list.
testcases.push(
    {
        "name" : "unit test",
        "skip" : true,
        "number" : "125",
        "function" : "genMissionWorkActinItems",
        "arguments" : [new Date("2023-01-01"), new Date(), 24],
        "expected" : true
    }
);

// this function generates related scheduled tasks for the day. basically in the format of 
testcases.push(
    {
        "name" : "unit test",
        "skip" : true,
        "number" : "130",
        "function" : "genBotWalkWithMissionActionItems",
        "arguments" : [new Date("2023-01-01"), new Date(), 24],
        "expected" : {
            "bid" : 0,
            "tz" : "eastern",
            "bw_works" : [],
            "other_works" : [],
        }
    }
);

//input: (b, bwworks, otherworks)
//
testcases.push(
    {
        "name" : "unit test",
        "skip" : true,
        "number" : "135",
        "function" : "genWalkWithMissionActionItems",
        "arguments" : [new Date("2023-01-01"), new Date(), 24],
        "expected" : {
            "mid" : 0,
            "name": "",
            "todos" : null,
            "cuspas" : null,      //customer platform, app, site  (for example: windows, chrome, amazon...)
            "start_time" : null
        }
    }
);


//generate number of pages to browse per product search.
//input: (task)
testcases.push(
    {
        "name" : "unit test",
        "skip" : true,
        "number" : "140",
        "function" : "gen_num_search",
        "arguments" : [{cuspas:"windows,adspower,amz"}],
        "expected" : 2
    }
);

//input: (bot, task)
// for bot, only care about levels. for task, care about name and cuspas
// level: site:level:role
testcases.push(
    {
        "name" : "unit test",
        "skip" : true,
        "number" : "145",
        "function" : "gen_num_page",
        "arguments" : [{levels: "amz:green:buyer"}, {name: "buy", "cuspas": "windows,adspower,amz"}],
        "expected" : 1
    }
);

testcases.push(
    {
        "name" : "unit test",
        "skip" : true,
        "number" : "14",
        "function" : "gen_num_page",
        "arguments" : [{levels: "amz:regular:buyer"}, {name: "buy", "cuspas": "windows,adspower,amz"}],
        "expected" : 2
    }
);


// generate number of products.
// input(pg, task)
testcases.push(
    {
        "name" : "unit test",
        "skip" : true,
        "number" : "150",
        "function" : "gen_num_product",
        "arguments" : [0, {cuspas:"windows,adspower,amz"}],
        "expected" : 3
    }
);

testcases.push(
    {
        "name" : "unit test",
        "skip" : true,
        "number" : "151",
        "function" : "gen_num_product",
        "arguments" : [1, {cuspas:"windows,adspower,amz"}],
        "expected" : 0
    }
);

testcases.push(
    {
        "name" : "unit test",
        "skip" : true,
        "number" : "152",
        "function" : "gen_num_product",
        "arguments" : [2, {cuspas:"windows,adspower,amz"}],
        "expected" : 1
    }
);

//randomely generate entry type:
//input: none
//output: entry type
testcases.push(
    {
        "name" : "unit test",
        "skip" : true,
        "number" : "155",
        "function" : "gen_entry_type",
        "arguments" : [],
        "expected" : "Search"
    }
);

//input: ecplatform
// output: randomely generated top menu item.
testcases.push(
    {
        "name" : "unit test",
        "skip" : true,
        "number" : "160",
        "function" : "gen_top_menu_item",
        "arguments" : ["amz"],
        "expected" : "Best Sellers"
    }
);

//input: none
// output: randomely generated flow type.
testcases.push(
    {
        "name" : "unit test",
        "skip" : true,
        "number" : "165",
        "function" : "gen_flow_type",
        "arguments" : [],
        "expected" : "down up down"
    }
);

//input: none
// output: randomely generated detail level.
testcases.push(
    {
        "name" : "unit test",
        "skip" : true,
        "number" : "170",
        "function" : "gen_detail_lvl",
        "arguments" : [],
        "expected" : 2
    }
);

//input: none
// output: randomely generated product selection.
testcases.push(
    {
        "name" : "unit test",
        "skip" : true,
        "number" : "175",
        "function" : "gen_prod_sel",
        "arguments" : [],
        "expected" : "mr"
    }
);


//input: none
// output: randomely generated buy steps.
testcases.push(
    {
        "name" : "unit test",
        "skip" : true,
        "number" : "180",
        "function" : "gen_buy_step",
        "arguments" : [],
        "expected" : true
    }
);


// genrate configuation
// input(bot, task, test_stub)
// output: configs for each search
//
//{
//   type: task.name,
//   site: task.site,
//   os: task.os,
//   app: task.app,
//   entry_paths: { 
//         type:  gen_entry_type(),                  // could be from "top main menu", "left main menu", or "search"
//         words: [],                                //why list of words here, because category->subcategory->subsubcategory...., need a list of words.
//   },
//   top_menu_item : gen_top_menu_item(task.site),   // this is the anchor name of the top menu item as the entrance point, for example "Computers", could also be | separated due to ebay and etsy, top main menu has sub-menu....
//   prodlist_pages: [],                             // list of configurations for the # of product list pages to browse. min: 1, max: 3, only browse up to top 3 pages.
//   buy_cfg: null
// }
// note: purchase step alwasys only available at the last product 
//
testcases.push(
    {
        "name" : "unit test",
        "skip" : true,
        "number" : "185",
        "function" : "gen_configuration",
        "arguments" : [{levels: "amz:green:buyer"}, 
        { name: "buy", cuspas: "win,chrome,amz"},
        {}],
        "expected" : [{
            type : "buy",
            site : "amz",
            os : "win",
            app : "chrome",
            entry_paths : {
                type : "search",
                words: "yoga pants"
            },
            top_menu_item : "",
            prodlist_pages : [
            {
                flow_type: "",
                products : [
                    {
                        selType: "cus",
                        detailLvl: "",
                        purchase: [
                            ""
                        ]
                    }
                ]
            }
            ],
            buy_cfg : ""
        }]
    }
);


//input: bot
//output: timezone
testcases.push(
    {
        "name" : "unit test",
        "skip" : true,
        "number" : "190",
        "function" : "get_bot_state_tz",
        "arguments" : [{location: "Austin, TX"}],
        "expected" : "central"
    }
);


//input: bot
//output: location state
testcases.push(
    {
        "name" : "unit test",
        "skip" : true,
        "number" : "195",
        "function" : "get_bot_state",
        "arguments" : [{location: "Austin, TX"}],
        "expected" : "tx"
    }
);

//input: (bots, task)
//output: state
testcases.push(
    {
        "name" : "unit test",
        "skip" : true,
        "number" : "200",
        "function" : "get_task_state",
        "arguments" : [new Date("2023-01-01"), new Date(), 24],
        "expected" : true
    }
);



//input: bots_tasks
// output: # of buy-walk tasks in a region...
testcases.push(
    {
        "name" : "unit test",
        "skip" : true,
        "number" : "210",
        "function" : "num_bw_tasks",
        "arguments" : [[{bw_works: [], other_works: []}]],
        "expected" : 0
    }
);

//get number of tasks in a group.
// input: grp
// output: 
testcases.push(
    {
        "name" : "unit test",
        "skip" : true,
        "number" : "215",
        "function" : "num_group_tasks",
        "arguments" : [{
            "eastern" : [{bw_works: [], other_works: []}],
            "central" : [{bw_works: [], other_works: []}],
            "mountain" : [{bw_works: [], other_works: []}],
            "pacific" : [{bw_works: [], other_works: []}],
            "alaska" : [{bw_works: [], other_works: []}],
            "hawaii" : [{bw_works: [], other_works: []}]
            }],
        "expected" : 0
    }
);

//get number of buy-walk tasks in a group.
// input: grp
// output: 
testcases.push(
    {
        "name" : "unit test",
        "skip" : true,
        "number" : "220",
        "function" : "num_group_bw_tasks",
        "arguments" : [{
            "eastern" : [{bw_works: [], other_works: []}],
            "central" : [{bw_works: [], other_works: []}],
            "mountain" : [{bw_works: [], other_works: []}],
            "pacific" : [{bw_works: [], other_works: []}],
            "alaska" : [{bw_works: [], other_works: []}],
            "hawaii" : [{bw_works: [], other_works: []}]
            }],
        "expected" : 0
    }
);

//get number of non-buy-walk tasks in a group.
// input: grp
// output: 
testcases.push(
    {
        "name" : "unit test",
        "skip" : true,
        "number" : "225",
        "function" : "num_other_tasks",
        "arguments" : [[{bw_works: [], other_works: []}]],
        "expected" : 0
    }
);

//input: tz, aslots
// output: available slots for buy-walk tasks
testcases.push(
    {
        "name" : "unit test",
        "skip" : true,
        "number" : "230",
        "function" : "gen_available_bw_slots",
        "arguments" : [new Date("2023-01-01"), new Date(), 24],
        "expected" : true
    }
);

//input: tz, aslots
// output: available slots for non-buy-walk tasks
testcases.push(
    {
        "name" : "unit test",
        "skip" : true,
        "number" : "235",
        "function" : "gen_available_other_slots",
        "arguments" : [new Date("2023-01-01"), new Date(), 24],
        "expected" : true
    }
);

//input: tz_bots_tasks_group, test_stub
// output: generate run time for the tasks.
// 1) 1 bot buy tasks in eastern region
// 2) 10 bot buy tasks in eastern region
// 3) 1/2 buy slots in eastern region occupied.
// 4) more than 1/2 buy slots in eastern region occupied.
// 5) more than 1/2 buy slots in eastern region occupied.

testcases.push(
    {
        "name" : "unit test",
        "skip" : true,
        "number" : "240",
        "function" : "genRunTime",
        "arguments" : [new Date("2023-01-01"), new Date(), 24],
        "expected" : true
    }
);

//input: (groups)
//output: count
testcases.push(
    {
        "name" : "unit test",
        "skip" : true,
        "number" : "245",
        "function" : "count_group_tasks",
        "arguments" : [[{
            "eastern" : [{bw_works: [], other_works: []}],
            "central" : [{bw_works: [], other_works: []}],
            "mountain" : [{bw_works: [], other_works: []}],
            "pacific" : [{bw_works: [], other_works: []}],
            "alaska" : [{bw_works: [], other_works: []}],
            "hawaii" : [{bw_works: [], other_works: []}]
            }]],
        "expected" : 0
    }
);

//input: allbtgs, bw_cap, i, j, work_type, test_stub
//output: [n, tzi, wj, (bw_cap-last_nbw)]
// 1) fetch first full cap of tasks within eastern region (i=0, j= 0)
// 2) fetch first full cap of tasks within partial region partial central (i=0, j= 0)
// 3) fetch first full cap of tasks within partial region partial central, partial hawaii (i=0, j= 0)
// 4) fetch first full cap of tasks exhaust all regions still couldn't fullfill capacity (i=0, j= 0)
// 5) fetch middle full cap of tasks exhaust all regions still couldn't fullfill capacity (i=eastern region, j= last of eastern)
// 6) fetch middle full cap of tasks exhaust all regions still couldn't fullfill capacity (i=pacific, j= last of pacific)
// 7) fetch last full cap of tasks exhaust all regions still couldn't fullfill capacity (i=pacific, j= last of pacific)
// 8) fetch full cap of tasks with out of range index. (i=pacific, j > # tasks in pacific)
// 9) fetch full cap of tasks with out of range index. (i > # of region, j > # tasks in pacific)

testcases.push(
    {
        "name" : "unit test",
        "skip" : true,
        "number" : "250",
        "function" : "get_n_bots_fill_work_capacity",
        "arguments" : [new Date("2023-01-01"), new Date(), 24],
        "expected" : true
    }
);

//input: (allbtgs, group, n, i, j, test_stub)
//output: [tzi, wj]
testcases.push(
    {
        "name" : "unit test",
        "skip" : true,
        "number" : "255",
        "function" : "add_n_bot_to_group",
        "arguments" : [new Date("2023-01-01"), new Date(), 24],
        "expected" : true
    }
);

//input: (bots, botstasks, test_stub)
// output: groups
testcases.push(
    {
        "name" : "unit test",
        "skip" : true,
        "number" : "260",
        "function" : "divideBotworksIntoGroups",
        "arguments" : [[
                {
                    bid : 0,
                    tz : "eastern",
                    bw_works : [{ config : {estRunTime: 1} }, { config : {estRunTime: 2} }, { config : {estRunTime: 3} }],
                    other_works : []
                },
                {
                    bid : 1,
                    tz : "eastern",
                    bw_works : [{ config : {estRunTime: 6} }, { config : {estRunTime: 5} }, { config : {estRunTime: 8} }],
                    other_works : []
                },
                {
                    bid : 3,
                    tz : "hawaii",
                    bw_works : [],
                    other_works : [{ config : {estRunTime: 10} }, { config : {estRunTime: 2} }]
                },
                {
                    bid : 4,
                    tz : "hawaii",
                    bw_works : [{ config : {estRunTime: 11} }, { config : {estRunTime: 12} }],
                    other_works : []
                },
                {
                    bid : 2,
                    tz : "eastern",
                    bw_works : [{ config : {estRunTime: 6} }, { config : {estRunTime: 6} }, { config : {estRunTime: 6} }],
                    other_works : []
                },
            ]
        , {testmode:false}],
        "expected" : [{
            "eastern" : [
                {
                    bid : 0,
                    bw_works : [{ config : {estRunTime: 1} }, { config : {estRunTime: 2} }, { config : {estRunTime: 3} }],
                    other_works : []
                }
            ],
            "central" : [
            ],
            "mountain" : [
            ],
            "pacific" : [
            ],
            "alaska" : [
            ],
            "hawaii" : [
                {
                    bid : 1,
                    bw_works : [],
                    other_works : [{ config : {estRunTime: 10} }, { config : {estRunTime: 2} }]
                }, 
                {
                    bid : 1,
                    bw_works : [],
                    other_works : [{ config : {estRunTime: 10} }, { config : {estRunTime: 2} }]
                }
            ]
        }]
    }
);

//create action items for today. 
//input: (bots, missions, callback, test_stub)
//output: task_groups
testcases.push(
    {
        "name" : "unit test",
        "skip" : true,
        "number" : "265",
        "functype" : "asyn",
        "function" : "genActionItems",
        "arguments" : [
            [], 
            [], 
            undefined, {testmode:false}],
        "expected" : []
    }
);


testcases.push(
    {
        "name" : "unit test",
        "skip" : true,
        "number" : "266",
        "functype" : "asyn",
        "function" : "genActionItems",
        "note" : "single bot, no incomplete buy, no incomplete walk, 1 routine walk generated, 1 new walk generated to add, no buy, no other",
        "arguments" : [
            [
                {
                    bid : 0,
                    owner : "abc@cde.com",
                    gender : "male",
                    levels : "amz:green:buyer,ebay:normal:seller",
                    location : "houston,tx",
                    roles : "amz:buyer,ebay:seller",
                    interests : "Electronics,Outdoors,Sports"
                },
                {
                    bid : 1,
                    owner : "abc@cde.com",
                    gender : "female",
                    levels : "amz:nomal:buyer",
                    location : "Honolulu,hi",
                    roles : "amz:buyer",
                    interests : "Sports"
                },
            ], 
            [
                {
                    mid : 0,
                    botid : 0,
                    ticket : "1",
                    owner : "abc@cde.com",
                    status : "COMPLETED",
                    type : "buy",
                    cuspas : "win,chrome,amz",
                    createon : "2023-01-30",
                    esttime : "1",
                    runtime : "",
                    trepeat : "once",
                    category  : "Sports",
                    phrase  : "yoga ball",
                    pseudoStore : "store0",
                    pseudoBrand : "brand0",
                    pseudoASIN : "12345",
                    esd : "2023-01-30",
                    ecd : "2023-01-31",
                    asd : "2023-01-30",
                    abd : "2023-01-30",
                    aad : "",
                    afd : "",
                    acd : "2023-01-31",
                    config  : "",
                    skills  : "win_chrome_amz_walk,win_chrome_amz_buy",
                    delDate  : ""
                },
                {
                    mid : 1,
                    botid : 1,
                    ticket : "2",
                    owner : "abc@cde.com",
                    status : "COMPLETED",
                    type : "buy",
                    cuspas : "win,chrome,amz",
                    createon : "2023-01-10",
                    esttime : "1",
                    runtime : "",
                    trepeat : "once",
                    category  : "Sports",
                    phrase  : "yoga ball",
                    pseudoStore : "store0",
                    pseudoBrand : "brand0",
                    pseudoASIN : "23456",
                    esd : "2023-01-24",
                    ecd : "2023-01-25",
                    asd : "2023-01-24",
                    abd : "2023-01-25",
                    aad : "",
                    afd : "",
                    acd : "2023-01-25",
                    config  : "",
                    skills  : "win_chrome_amz_walk,win_chrome_amz_buy",
                    delDate  : ""
                },
                {
                    mid : 4,
                    botid : 0,
                    ticket : "3",
                    owner : "abc@cde.com",
                    status : "ASSIGNED",
                    type : "buy",
                    cuspas : "win,chrome,amz",
                    createon : "2023-01-30",
                    esttime : "1",
                    runtime : "",
                    trepeat : "once",
                    category  : "Sports",
                    phrase  : "yoga ball",
                    pseudoStore : "store1",
                    pseudoBrand : "brand1",
                    pseudoASIN : "56789",
                    esd : "2023-02-02 00:00:00",
                    ecd : "2023-02-02 00:00:00",
                    asd : "2023-02-02 00:00:00",
                    abd : "2023-02-02 00:00:00",
                    acd : "2023-02-02 00:00:00",
                    afd : "2023-02-02 00:00:00",
                    acd : "2023-02-02 00:00:00",
                    config  : "",
                    skills  : "win_chrome_amz_walk,win_chrome_amz_buy",
                    delDate  : ""
                },
                {
                    mid : 6,
                    botid : 1,
                    ticket : "4",
                    owner : "abc@cde.com",
                    status : "ASSIGNED",
                    type : "buy",
                    cuspas : "win,chrome,amz",
                    createon : "2023-01-30",
                    esttime : "1",
                    runtime : "",
                    trepeat : "once",
                    category  : "Sports",
                    phrase  : "dumb bell",
                    pseudoStore : "store1",
                    pseudoBrand : "brand1",
                    pseudoASIN : "67890",
                    esd : "2023-02-02 00:00:00",
                    ecd : "2023-02-02 00:00:00",
                    asd : "2023-02-02 00:00:00",
                    abd : "2023-02-02 00:00:00",
                    acd : "2023-02-02 00:00:00",
                    afd : "2023-02-02 00:00:00",
                    acd : "2023-02-02 00:00:00",
                    config  : "",
                    skills  : "win_chrome_amz_walk,win_chrome_amz_buy",
                    delDate  : ""
                },
                {
                    mid : 7,
                    botid : 0,
                    ticket : "5",
                    owner : "abc@cde.com",
                    status : "ASSIGNED",
                    type : "sell",
                    cuspas : "win,chrome,amz",
                    createon : "2023-01-30",
                    esttime : "10",
                    runtime : "",
                    trepeat : "daily",
                    category  : "",
                    phrase  : "",
                    pseudoStore : "",
                    pseudoBrand : "",
                    pseudoASIN : "",
                    esd : "",
                    ecd : "",
                    asd : "",
                    abd : "",
                    acd : "",
                    afd : "",
                    acd : "",
                    config  : "",
                    skills  : "win_chrome_ebay_sell, win_chrome_custom0_buy_label",
                    delDate  : ""
                }
            ], 
            undefined, {testmode:false}],
        "expected" : []
    }
);



//input: (owner, inSettings, callback, logFlag, test_stub)
// output: task_groups
//  1) 
//      a)
//          i)
//          ii)
//
//      b)
testcases.push(
    {
        "name" : "unit test",
        "skip" : true,
        "number" : "270",
        "function" : "genSchedule",
        "testmode" : true,
        "skip_getBots" : true,
        "skip_getMissions" : true,
        "getBots" : {
            "numberOfRecordsUpdated": 0,
            "records": [
                [
                    {
                        "longValue": 2
                    },
                    {
                        "stringValue": "songc@yahoo.com"
                    },
                    {
                        "stringValue": "amz:green:buyer,ebay:green:buyer,etsy:green:buyer"
                    },
                    {
                        "stringValue": "2022-09-06"
                    },
                    {
                        "stringValue": "male"
                    },
                    {
                        "stringValue": "2022-10-06"
                    },
                    {
                        "stringValue": "Pet_Supplies,Smart Home,Sports,Electronics,Outdoors"
                    },
                    {
                        "stringValue": "austin, texas"
                    },
                    {
                        "stringValue": "buyer"
                    },
                    {
                        "stringValue": "en"
                    },
                    {
                        "stringValue": "2022-10-06"
                    }
                ],
                [
                    {
                        "longValue": 3
                    },
                    {
                        "stringValue": "songc@yahoo.com"
                    },
                    {
                        "stringValue": "amz:green:buyer,ebay:green:buyer,etsy:green:buyer"
                    },
                    {
                        "stringValue": "2022-10-07"
                    },
                    {
                        "stringValue": "male"
                    },
                    {
                        "stringValue": "2022-10-07"
                    },
                    {
                        "stringValue": "Smart Home,Bearuty_Health,Automobile_Industrial,Toys_Kids_Baby,Home_Garden_Tools"
                    },
                    {
                        "stringValue": "austin, texas"
                    },
                    {
                        "stringValue": "b"
                    },
                    {
                        "stringValue": "en"
                    },
                    {
                        "stringValue": "2522-10-07"
                    }
                ]
            ]
        },
        "getMissions" : {
            "numberOfRecordsUpdated": 0,
            "records": [
                [
                    {
                        "longValue": 21
                    },
                    {
                        "isNull": true
                    },
                    {
                        "stringValue": "songc@yahoo.com"
                    },
                    {
                        "longValue": 2
                    },
                    {
                        "stringValue": "ASSIGNED"
                    },
                    {
                        "stringValue": "2022-10-12 00:00:00"
                    },
                    {
                        "stringValue": "2022-10-13 00:00:00"
                    },
                    {
                        "stringValue": "2022-10-13 00:00:00"
                    },
                    {
                        "stringValue": "2522-10-12 00:00:00"
                    },
                    {
                        "stringValue": "2522-10-12 00:00:00"
                    },
                    {
                        "stringValue": "2522-10-12 00:00:00"
                    },
                    {
                        "stringValue": "2522-10-12 00:00:00"
                    },
                    {
                        "stringValue": "2522-10-12 00:00:00"
                    },
                    {
                        "isNull": true
                    },
                    {
                        "isNull": true
                    },
                    {
                        "isNull": true
                    },
                    {
                        "isNull": true
                    },
                    {
                        "stringValue": "Sports"
                    },
                    {
                        "stringValue": "yoga ball"
                    },
                    {
                        "stringValue": "apple"
                    },
                    {
                        "stringValue": "apple"
                    },
                    {
                        "stringValue": "12345"
                    },
                    {
                        "stringValue": "buy"
                    },
                    {
                        "isNull": true
                    },
                    {
                        "isNull": true
                    },
                    {
                        "stringValue": "2522-10-12 00:00:00"
                    }
                ],
                [
                    {
                        "longValue": 26
                    },
                    {
                        "isNull": true
                    },
                    {
                        "stringValue": "songc@yahoo.com"
                    },
                    {
                        "longValue": 2
                    },
                    {
                        "stringValue": "ASSIGNED"
                    },
                    {
                        "stringValue": "2022-10-22 00:00:00"
                    },
                    {
                        "stringValue": "2022-10-22 00:00:00"
                    },
                    {
                        "stringValue": "2022-10-22 00:00:00"
                    },
                    {
                        "stringValue": "2522-10-22 00:00:00"
                    },
                    {
                        "stringValue": "2522-10-22 00:00:00"
                    },
                    {
                        "stringValue": "2522-10-22 00:00:00"
                    },
                    {
                        "stringValue": "2522-10-22 00:00:00"
                    },
                    {
                        "stringValue": "2522-10-22 00:00:00"
                    },
                    {
                        "isNull": true
                    },
                    {
                        "isNull": true
                    },
                    {
                        "isNull": true
                    },
                    {
                        "isNull": true
                    },
                    {
                        "stringValue": ""
                    },
                    {
                        "stringValue": ""
                    },
                    {
                        "stringValue": ""
                    },
                    {
                        "stringValue": ""
                    },
                    {
                        "stringValue": ""
                    },
                    {
                        "stringValue": "Browse"
                    },
                    {
                        "isNull": true
                    },
                    {
                        "isNull": true
                    },
                    {
                        "stringValue": "2522-10-22 00:00:00"
                    }
                ],
                [
                    {
                        "longValue": 27
                    },
                    {
                        "isNull": true
                    },
                    {
                        "stringValue": "songc@yahoo.com"
                    },
                    {
                        "longValue": 3
                    },
                    {
                        "stringValue": "ASSIGNED"
                    },
                    {
                        "stringValue": "2022-10-22 00:00:00"
                    },
                    {
                        "stringValue": "2022-10-22 00:00:00"
                    },
                    {
                        "stringValue": "2022-10-22 00:00:00"
                    },
                    {
                        "stringValue": "3022-10-22 00:00:00"
                    },
                    {
                        "stringValue": "3022-10-22 00:00:00"
                    },
                    {
                        "stringValue": "3022-10-22 00:00:00"
                    },
                    {
                        "stringValue": "3022-10-22 00:00:00"
                    },
                    {
                        "stringValue": "3022-10-22 00:00:00"
                    },
                    {
                        "isNull": true
                    },
                    {
                        "isNull": true
                    },
                    {
                        "isNull": true
                    },
                    {
                        "isNull": true
                    },
                    {
                        "stringValue": ""
                    },
                    {
                        "stringValue": ""
                    },
                    {
                        "stringValue": ""
                    },
                    {
                        "stringValue": ""
                    },
                    {
                        "stringValue": ""
                    },
                    {
                        "stringValue": "Browse"
                    },
                    {
                        "isNull": true
                    },
                    {
                        "isNull": true
                    },
                    {
                        "stringValue": "3022-10-22 00:00:00"
                    }
                ],
                [
                    {
                        "longValue": 28
                    },
                    {
                        "isNull": true
                    },
                    {
                        "stringValue": "songc@yahoo.com"
                    },
                    {
                        "longValue": 2
                    },
                    {
                        "stringValue": "ASSIGNED"
                    },
                    {
                        "stringValue": "2022-10-23 00:00:00"
                    },
                    {
                        "stringValue": "2022-10-23 00:00:00"
                    },
                    {
                        "stringValue": "2022-10-23 00:00:00"
                    },
                    {
                        "stringValue": "2522-10-23 00:00:00"
                    },
                    {
                        "stringValue": "2522-10-23 00:00:00"
                    },
                    {
                        "stringValue": "2522-10-23 00:00:00"
                    },
                    {
                        "stringValue": "2522-10-23 00:00:00"
                    },
                    {
                        "stringValue": "2522-10-23 00:00:00"
                    },
                    {
                        "isNull": true
                    },
                    {
                        "isNull": true
                    },
                    {
                        "isNull": true
                    },
                    {
                        "isNull": true
                    },
                    {
                        "stringValue": ""
                    },
                    {
                        "stringValue": ""
                    },
                    {
                        "stringValue": ""
                    },
                    {
                        "stringValue": ""
                    },
                    {
                        "stringValue": ""
                    },
                    {
                        "stringValue": "Browse"
                    },
                    {
                        "isNull": true
                    },
                    {
                        "isNull": true
                    },
                    {
                        "stringValue": "2522-10-23 00:00:00"
                    }
                ],
                [
                    {
                        "longValue": 29
                    },
                    {
                        "isNull": true
                    },
                    {
                        "stringValue": "songc@yahoo.com"
                    },
                    {
                        "longValue": 3
                    },
                    {
                        "stringValue": "ASSIGNED"
                    },
                    {
                        "stringValue": "2022-10-23 00:00:00"
                    },
                    {
                        "stringValue": "2022-10-23 00:00:00"
                    },
                    {
                        "stringValue": "2022-10-23 00:00:00"
                    },
                    {
                        "stringValue": "3022-10-23 00:00:00"
                    },
                    {
                        "stringValue": "3022-10-23 00:00:00"
                    },
                    {
                        "stringValue": "3022-10-23 00:00:00"
                    },
                    {
                        "stringValue": "3022-10-23 00:00:00"
                    },
                    {
                        "stringValue": "3022-10-23 00:00:00"
                    },
                    {
                        "isNull": true
                    },
                    {
                        "isNull": true
                    },
                    {
                        "isNull": true
                    },
                    {
                        "isNull": true
                    },
                    {
                        "stringValue": ""
                    },
                    {
                        "stringValue": ""
                    },
                    {
                        "stringValue": ""
                    },
                    {
                        "stringValue": ""
                    },
                    {
                        "stringValue": ""
                    },
                    {
                        "stringValue": "Browse"
                    },
                    {
                        "isNull": true
                    },
                    {
                        "isNull": true
                    },
                    {
                        "stringValue": "3022-10-23 00:00:00"
                    }
                ],
                [
                    {
                        "longValue": 30
                    },
                    {
                        "isNull": true
                    },
                    {
                        "stringValue": "songc@yahoo.com"
                    },
                    {
                        "longValue": 2
                    },
                    {
                        "stringValue": "ASSIGNED"
                    },
                    {
                        "stringValue": "2022-10-23 00:00:00"
                    },
                    {
                        "stringValue": "2022-10-23 00:00:00"
                    },
                    {
                        "stringValue": "2022-10-23 00:00:00"
                    },
                    {
                        "stringValue": "2522-10-23 00:00:00"
                    },
                    {
                        "stringValue": "2522-10-23 00:00:00"
                    },
                    {
                        "stringValue": "2522-10-23 00:00:00"
                    },
                    {
                        "stringValue": "2522-10-23 00:00:00"
                    },
                    {
                        "stringValue": "2522-10-23 00:00:00"
                    },
                    {
                        "isNull": true
                    },
                    {
                        "isNull": true
                    },
                    {
                        "isNull": true
                    },
                    {
                        "isNull": true
                    },
                    {
                        "stringValue": ""
                    },
                    {
                        "stringValue": ""
                    },
                    {
                        "stringValue": ""
                    },
                    {
                        "stringValue": ""
                    },
                    {
                        "stringValue": ""
                    },
                    {
                        "stringValue": "Browse"
                    },
                    {
                        "isNull": true
                    },
                    {
                        "isNull": true
                    },
                    {
                        "stringValue": "2522-10-23 00:00:00"
                    }
                ],
                [
                    {
                        "longValue": 31
                    },
                    {
                        "isNull": true
                    },
                    {
                        "stringValue": "songc@yahoo.com"
                    },
                    {
                        "longValue": 3
                    },
                    {
                        "stringValue": "ASSIGNED"
                    },
                    {
                        "stringValue": "2022-10-23 00:00:00"
                    },
                    {
                        "stringValue": "2022-10-23 00:00:00"
                    },
                    {
                        "stringValue": "2022-10-23 00:00:00"
                    },
                    {
                        "stringValue": "3022-10-23 00:00:00"
                    },
                    {
                        "stringValue": "3022-10-23 00:00:00"
                    },
                    {
                        "stringValue": "3022-10-23 00:00:00"
                    },
                    {
                        "stringValue": "3022-10-23 00:00:00"
                    },
                    {
                        "stringValue": "3022-10-23 00:00:00"
                    },
                    {
                        "isNull": true
                    },
                    {
                        "isNull": true
                    },
                    {
                        "isNull": true
                    },
                    {
                        "isNull": true
                    },
                    {
                        "stringValue": ""
                    },
                    {
                        "stringValue": ""
                    },
                    {
                        "stringValue": ""
                    },
                    {
                        "stringValue": ""
                    },
                    {
                        "stringValue": ""
                    },
                    {
                        "stringValue": "Browse"
                    },
                    {
                        "isNull": true
                    },
                    {
                        "isNull": true
                    },
                    {
                        "stringValue": "3022-10-23 00:00:00"
                    }
                ],
                [
                    {
                        "longValue": 32
                    },
                    {
                        "isNull": true
                    },
                    {
                        "stringValue": "songc@yahoo.com"
                    },
                    {
                        "longValue": 2
                    },
                    {
                        "stringValue": "ASSIGNED"
                    },
                    {
                        "stringValue": "2022-10-23 00:00:00"
                    },
                    {
                        "stringValue": "2022-10-23 00:00:00"
                    },
                    {
                        "stringValue": "2022-10-23 00:00:00"
                    },
                    {
                        "stringValue": "2522-10-23 00:00:00"
                    },
                    {
                        "stringValue": "2522-10-23 00:00:00"
                    },
                    {
                        "stringValue": "2522-10-23 00:00:00"
                    },
                    {
                        "stringValue": "2522-10-23 00:00:00"
                    },
                    {
                        "stringValue": "2522-10-23 00:00:00"
                    },
                    {
                        "isNull": true
                    },
                    {
                        "isNull": true
                    },
                    {
                        "isNull": true
                    },
                    {
                        "isNull": true
                    },
                    {
                        "stringValue": ""
                    },
                    {
                        "stringValue": ""
                    },
                    {
                        "stringValue": ""
                    },
                    {
                        "stringValue": ""
                    },
                    {
                        "stringValue": ""
                    },
                    {
                        "stringValue": "Browse"
                    },
                    {
                        "isNull": true
                    },
                    {
                        "isNull": true
                    },
                    {
                        "stringValue": "2522-10-23 00:00:00"
                    }
                ],
                [
                    {
                        "longValue": 33
                    },
                    {
                        "isNull": true
                    },
                    {
                        "stringValue": "songc@yahoo.com"
                    },
                    {
                        "longValue": 3
                    },
                    {
                        "stringValue": "ASSIGNED"
                    },
                    {
                        "stringValue": "2022-10-23 00:00:00"
                    },
                    {
                        "stringValue": "2022-10-23 00:00:00"
                    },
                    {
                        "stringValue": "2022-10-23 00:00:00"
                    },
                    {
                        "stringValue": "3022-10-23 00:00:00"
                    },
                    {
                        "stringValue": "3022-10-23 00:00:00"
                    },
                    {
                        "stringValue": "3022-10-23 00:00:00"
                    },
                    {
                        "stringValue": "3022-10-23 00:00:00"
                    },
                    {
                        "stringValue": "3022-10-23 00:00:00"
                    },
                    {
                        "isNull": true
                    },
                    {
                        "isNull": true
                    },
                    {
                        "isNull": true
                    },
                    {
                        "isNull": true
                    },
                    {
                        "stringValue": ""
                    },
                    {
                        "stringValue": ""
                    },
                    {
                        "stringValue": ""
                    },
                    {
                        "stringValue": ""
                    },
                    {
                        "stringValue": ""
                    },
                    {
                        "stringValue": "Browse"
                    },
                    {
                        "isNull": true
                    },
                    {
                        "isNull": true
                    },
                    {
                        "stringValue": "3022-10-23 00:00:00"
                    }
                ],
                [
                    {
                        "longValue": 34
                    },
                    {
                        "isNull": true
                    },
                    {
                        "stringValue": "songc@yahoo.com"
                    },
                    {
                        "longValue": 2
                    },
                    {
                        "stringValue": "ASSIGNED"
                    },
                    {
                        "stringValue": "2022-10-23 00:00:00"
                    },
                    {
                        "stringValue": "2022-10-23 00:00:00"
                    },
                    {
                        "stringValue": "2022-10-23 00:00:00"
                    },
                    {
                        "stringValue": "2522-10-23 00:00:00"
                    },
                    {
                        "stringValue": "2522-10-23 00:00:00"
                    },
                    {
                        "stringValue": "2522-10-23 00:00:00"
                    },
                    {
                        "stringValue": "2522-10-23 00:00:00"
                    },
                    {
                        "stringValue": "2522-10-23 00:00:00"
                    },
                    {
                        "isNull": true
                    },
                    {
                        "isNull": true
                    },
                    {
                        "isNull": true
                    },
                    {
                        "isNull": true
                    },
                    {
                        "stringValue": ""
                    },
                    {
                        "stringValue": ""
                    },
                    {
                        "stringValue": ""
                    },
                    {
                        "stringValue": ""
                    },
                    {
                        "stringValue": ""
                    },
                    {
                        "stringValue": "Browse"
                    },
                    {
                        "isNull": true
                    },
                    {
                        "isNull": true
                    },
                    {
                        "stringValue": "2522-10-23 00:00:00"
                    }
                ],
                [
                    {
                        "longValue": 35
                    },
                    {
                        "isNull": true
                    },
                    {
                        "stringValue": "songc@yahoo.com"
                    },
                    {
                        "longValue": 3
                    },
                    {
                        "stringValue": "ASSIGNED"
                    },
                    {
                        "stringValue": "2022-10-23 00:00:00"
                    },
                    {
                        "stringValue": "2022-10-23 00:00:00"
                    },
                    {
                        "stringValue": "2022-10-23 00:00:00"
                    },
                    {
                        "stringValue": "3022-10-23 00:00:00"
                    },
                    {
                        "stringValue": "3022-10-23 00:00:00"
                    },
                    {
                        "stringValue": "3022-10-23 00:00:00"
                    },
                    {
                        "stringValue": "3022-10-23 00:00:00"
                    },
                    {
                        "stringValue": "3022-10-23 00:00:00"
                    },
                    {
                        "isNull": true
                    },
                    {
                        "isNull": true
                    },
                    {
                        "isNull": true
                    },
                    {
                        "isNull": true
                    },
                    {
                        "stringValue": ""
                    },
                    {
                        "stringValue": ""
                    },
                    {
                        "stringValue": ""
                    },
                    {
                        "stringValue": ""
                    },
                    {
                        "stringValue": ""
                    },
                    {
                        "stringValue": "Browse"
                    },
                    {
                        "isNull": true
                    },
                    {
                        "isNull": true
                    },
                    {
                        "stringValue": "3022-10-23 00:00:00"
                    }
                ],
                [
                    {
                        "longValue": 36
                    },
                    {
                        "isNull": true
                    },
                    {
                        "stringValue": "songc@yahoo.com"
                    },
                    {
                        "longValue": 2
                    },
                    {
                        "stringValue": "ASSIGNED"
                    },
                    {
                        "stringValue": "2022-11-01 00:00:00"
                    },
                    {
                        "stringValue": "2022-11-01 00:00:00"
                    },
                    {
                        "stringValue": "2022-11-01 00:00:00"
                    },
                    {
                        "stringValue": "2522-11-01 00:00:00"
                    },
                    {
                        "stringValue": "2522-11-01 00:00:00"
                    },
                    {
                        "stringValue": "2522-11-01 00:00:00"
                    },
                    {
                        "stringValue": "2522-11-01 00:00:00"
                    },
                    {
                        "stringValue": "2522-11-01 00:00:00"
                    },
                    {
                        "isNull": true
                    },
                    {
                        "isNull": true
                    },
                    {
                        "isNull": true
                    },
                    {
                        "isNull": true
                    },
                    {
                        "stringValue": ""
                    },
                    {
                        "stringValue": ""
                    },
                    {
                        "stringValue": ""
                    },
                    {
                        "stringValue": ""
                    },
                    {
                        "stringValue": ""
                    },
                    {
                        "stringValue": "Browse"
                    },
                    {
                        "isNull": true
                    },
                    {
                        "isNull": true
                    },
                    {
                        "stringValue": "2522-11-01 00:00:00"
                    }
                ]
            ]
        }
    }
);


//randomly pick a bot's interest category based on gender
// input: (gend, existing, test_stub)
// output: interest
testcases.push(
    {
        "name" : "unit test",
        "skip" : true,
        "number" : "275",
        "function" : "createBotInterest",
        "arguments" : [{gender: "female"}, ["Outdoors", "Beauty_Health"], {testmode: false}],
        "expected" : "Outdoors"
    }
);

// this function assign 3 more interest areas to the bot. 
// input: (botData, callback, logFlag, test_stub)
// output: 
testcases.push(
    {
        "name" : "unit test",
        "skip" : true,
        "number" : "280",
        "function" : "assignInterestsToBots",
        "arguments" : [new Date("2023-01-01"), new Date(), 24],
        "expected" : true
    }
);


//input: (botData, rawInput, callback, logFlag, test_stub)
//output: 
testcases.push(
    {
        "name" : "unit test",
        "skip" : true,
        "number" : "285",
        "function" : "prepareAddBots",
        "arguments" : [[
            ], {identity : { claims : {email : "abc@cde.com"}}}, 
            null, 
            true, 
            {testmode: false, skip_prepareAddBots: false, prepareAddBots : []} 
        ],
        "expected" : [{
            
        }]
    }
);


//input: (missionData, rawInput, callback, logFlag, test_stub)
// rawInput = {identity : { claims : {email : "abc@cde.com"}}}
//output: 
testcases.push(
    {
        "name" : "unit test",
        "skip" : true,
        "number" : "290",
        "function" : "prepareAddMissions",
        "arguments" : [ [
            ], {identity : { claims : {email : "abc@cde.com"}}}, 
            null, 
            true, 
            {testmode: false, skip_prepareAddMissions: false, prepareAddMissions : []} 
        ],
        "expected" : [{
            
        }]
    }
);

// check whether btos need to be upgraded.... in level
//input: (bots, missions, test_stub)
//output: updated bot level information
testcases.push(
    {
        "name" : "unit test",
        "skip" : true,
        "number" : "295",
        "function" : "findBotsNeedToUpgrade",
        "arguments" : [new Date("2023-01-01"), new Date(), 24],
        "expected" : true
    }
);


testcases.push(
    {
        "name" : "functional test",
        "skip" : true,
        "number" : "300",
        "function" : "addBots",
        "arguments" : [new Date("2023-01-01"), new Date(), 24],
        "expected" : true
    }
);

testcases.push(
    {
        "name" : "functional test",
        "skip" : true,
        "number" : "305",
        "function" : "addMissions",
        "arguments" : [new Date("2023-01-01"), new Date(), 24],
        "expected" : true
    }
);

testcases.push(
    {
        "name" : "functional test",
        "skip" : true,
        "number" : "310",
        "function" : "queryMissions",
        "arguments" : [new Date("2023-01-01"), new Date(), 24],
        "expected" : true
    }
);

testcases.push(
    {
        "name" : "functional test",
        "skip" : true,
        "number" : "315",
        "function" : "queryMissions",
        "arguments" : [new Date("2023-01-01"), new Date(), 24],
        "expected" : true
    }
);

testcases.push(
    {
        "name" : "functional test",
        "skip" : true,
        "number" : "320",
        "function" : "queryMissions",
        "arguments" : [new Date("2023-01-01"), new Date(), 24],
        "expected" : true
    }
);

testcases.push(
    {
        "name" : "functional test",
        "skip" : true,
        "number" : "325",
        "function" : "queryMissions",
        "arguments" : [new Date("2023-01-01"), new Date(), 24],
        "expected" : true
    }
);

testcases.push(
    {
        "name" : "functional test",
        "skip" : true,
        "number" : "330",
        "function" : "removeBots",
        "arguments" : [new Date("2023-01-01"), new Date(), 24],
        "expected" : true
    }
);

testcases.push(
    {
        "name" : "functional test",
        "skip" : true,
        "number" : "335",
        "function" : "removeMissions",
        "arguments" : [new Date("2023-01-01"), new Date(), 24],
        "expected" : true
    }
);


testcases.push(
    {
        "name" : "functional test",
        "skip" : true,
        "number" : "340",
        "function" : "updateBots",
        "arguments" : [new Date("2023-01-01"), new Date(), 24],
        "expected" : true
    }
);


testcases.push(
    {
        "name" : "functional test",
        "skip" : true,
        "number" : "345",
        "function" : "updateMissions",
        "arguments" : [new Date("2023-01-01"), new Date(), 24],
        "expected" : true
    }
);


testcases.push(
    {
        "name" : "functional test",
        "skip" : true,
        "number" : "350",
        "function" : "updateWorkResults",
        "arguments" : [new Date("2023-01-01"), new Date(), 24],
        "expected" : true
    }
);

testcases.push(
    {
        "name" : "functional test",
        "skip" : true,
        "number" : "400",
        "function" : "findNextAvailableSlot",
        "arguments" : [1, [], 0, 0],
        "expected" : -1
    }
);

testcases.push(
    {
        "name" : "functional test",
        "skip" : true,
        "number" : "401",
        "function" : "findNextAvailableSlot",
        "arguments" : [1, [1], 0, 0],
        "expected" : 1
    }
);

testcases.push(
    {
        "name" : "functional test",
        "skip" : true,
        "number" : "402",
        "function" : "findNextAvailableSlot",
        "arguments" : [2, [1], 0, 0],
        "expected" : -1
    }
);

testcases.push(
    {
        "name" : "functional test",
        "skip" : true,
        "number" : "403",
        "function" : "findNextAvailableSlot",
        "arguments" : [2, [1,2], 0, 1],
        "expected" : 0
    }
);

testcases.push(
    {
        "name" : "functional test",
        "skip" : true,
        "number" : "404",
        "function" : "findNextAvailableSlot",
        "arguments" : [2, [1,3], 0, 1],
        "expected" : -1
    }
);

testcases.push(
    {
        "name" : "functional test",
        "skip" : true,
        "number" : "405",
        "function" : "findNextAvailableSlot",
        "arguments" : [2, [1,3,4], 0, 2],
        "expected" : 1
    }
);

testcases.push(
    {
        "name" : "functional test",
        "skip" : true,
        "number" : "406",
        "function" : "findNextAvailableSlot",
        "arguments" : [2, [1,3,6,7,8], 1, 3],
        "expected" : 2
    }
);

testcases.push(
    {
        "name" : "functional test",
        "skip" : true,
        "number" : "407",
        "function" : "findNextAvailableSlot",
        "arguments" : [2, [1,3,6,7,9], 0, 4],
        "expected" : 2
    }
);


testcases.push(
    {
        "name" : "functional test",
        "skip" : true,
        "number" : "410",
        "function" : "fill_day_capacity",
        "arguments" : [{
            "eastern" : [],
            "central" : [],
            "mountain" : [],
            "pacific" : [],
            "alaska" : [],
            "hawaii" : []
        }],
        "expected" : {
            "eastern" : [],
            "central" : [],
            "mountain" : [],
            "pacific" : [],
            "alaska" : [],
            "hawaii" : []
        }
    }
);


testcases.push(
    {
        "name" : "functional test",
        "skip" : true,
        "number" : "411",
        "function" : "fill_day_capacity",
        "arguments" : [{
            "eastern" : [
                {
                    bid : 0,
                    bw_works : [{ config : {estRunTime: 1} }, { config : {estRunTime: 2} }, { config : {estRunTime: 3} }],
                    other_works : []
                }
            ],
            "central" : [
            ],
            "mountain" : [
            ],
            "pacific" : [
            ],
            "alaska" : [
            ],
            "hawaii" : [
                {
                    bid : 1,
                    bw_works : [],
                    other_works : [{ config : {estRunTime: 1} }, { config : {estRunTime: 2} }]
                }
            ]
        }],
        "expected" : {
            "eastern" : [
                {
                    bid : 0,
                    bw_works : [{ config : {estRunTime: 1} }, { config : {estRunTime: 2} }, { config : {estRunTime: 3} }],
                    other_works : []
                }
            ],
            "central" : [
            ],
            "mountain" : [
            ],
            "pacific" : [
            ],
            "alaska" : [
            ],
            "hawaii" : [
                {
                    bid : 1,
                    bw_works : [],
                    other_works : [{ config : {estRunTime: 1} }, { config : {estRunTime: 2} }]
                }
            ]
        }
    }
);



testcases.push(
    {
        "name" : "functional test",
        "skip" : true,
        "number" : "412",
        "function" : "fill_day_capacity",
        "arguments" : [{
            "eastern" : [
                {
                    bid : 0,
                    bw_works : [{ config : {estRunTime: 1} }, { config : {estRunTime: 2} }, { config : {estRunTime: 3} }],
                    other_works : []
                },
                {
                    bid : 1,
                    bw_works : [{ config : {estRunTime: 6} }, { config : {estRunTime: 5} }, { config : {estRunTime: 8} }],
                    other_works : []
                },
                {
                    bid : 2,
                    bw_works : [{ config : {estRunTime: 6} }, { config : {estRunTime: 6} }, { config : {estRunTime: 6} }],
                    other_works : []
                }
            ],
            "central" : [
            ],
            "mountain" : [
            ],
            "pacific" : [
            ],
            "alaska" : [
            ],
            "hawaii" : [
                {
                    bid : 3,
                    bw_works : [],
                    other_works : [{ config : {estRunTime: 10} }, { config : {estRunTime: 2} }]
                },
                {
                    bid : 4,
                    bw_works : [{ config : {estRunTime: 11} }, { config : {estRunTime: 12} }],
                    other_works : []
                }
            ]
        }],
        "expected" : {
            "eastern" : [
                {
                    bid : 0,
                    bw_works : [{ config : {estRunTime: 1} }, { config : {estRunTime: 2} }, { config : {estRunTime: 3} }],
                    other_works : []
                }
            ],
            "central" : [
            ],
            "mountain" : [
            ],
            "pacific" : [
            ],
            "alaska" : [
            ],
            "hawaii" : [
                {
                    bid : 1,
                    bw_works : [],
                    other_works : [{ config : {estRunTime: 10} }, { config : {estRunTime: 2} }]
                }, 
                {
                    bid : 1,
                    bw_works : [],
                    other_works : [{ config : {estRunTime: 10} }, { config : {estRunTime: 2} }]
                }
            ]
        }
    }
);



testcases.push(
    {
        "name" : "functional test",
        "skip" : true,
        "number" : "420",
        "function" : "isGroupEmpty",
        "arguments" : [{
            "eastern" : [],
            "central" : [],
            "mountain" : [],
            "pacific" : [],
            "alaska" : [],
            "hawaii" : []
        }],
        "expected" : true
    }
);

testcases.push(
    {
        "name" : "functional test",
        "skip" : true,
        "number" : "421",
        "function" : "isGroupEmpty",
        "arguments" : [{
            "eastern" : [],
            "central" : [],
            "mountain" : [],
            "pacific" : [],
            "alaska" : [],
            "hawaii" : [{ "bw_works" : [], "other_works" : [] }]
        }],
        "expected" : false
    }
);



testcases.push(
    {
        "name" : "functional test",
        "skip" : true,
        "number" : "425",
        "function" : "botTaskEstRunTime",
        "arguments" : [{
            "bw_works" : [{ config : {estRunTime: 1} }, { config : {estRunTime: 2} }, { config : {estRunTime: 3} }],
            "other_works" : [{ config : {estRunTime: 1} }]
        }],
        "expected" : 7
    }
);

testcases.push(
    {
        "name" : "functional test",
        "skip" : true,
        "number" : "426",
        "function" : "exports.handler",
        "arguments" : [],
        "expected" : 6
    }
);

testcases.push(
    {
        "name" : "bypass test",
        "skip" : true,
        "number" : "4000",
        "function" : "sum_est_run_time",
        "arguments" : [[{ config : {estRunTime: 1} }, { config : {estRunTime: 2} }, { config : {estRunTime: 3} }]],
        "expected" : {
            "task_groups" : 
                [
                    {
                        "eastern" : [],
                        "central" : [], 
                        "mountain" : [], 
                        "pacific" : [
                            {
                              bid : 2,
                              tz : "pacific",
                              bw_works : [
                              ],
                              other_works : [
                                  {
                                      mid : 2,
                                      name: "sell",
                                      todos : [],
                                      cuspas : "win,ads,ebay",
                                      config : {
                                          estRunTime : 1
                                      },
                                      start_time : 1
                                  }
                              ],
                            }
                        ], 
                        "alaska" : [], 
                        "hawaii" : []
                    }
                ],
            "added_missions" : [
                {
                    mid : 2,
                    owner : "songc@yahoo.com",
                    botid : 2,
                    ticket : 0,
                    status : "Scheduled",
                    createon : "2023-05-21 00:00:00",
                    esd : "2023-05-21 00:00:00",
                    ecd  : "2023-05-21 00:00:00",
                    asd  : "2023-05-21 00:00:00",
                    abd  : "2023-05-21 00:00:00",
                    aad  : "2023-05-21 00:00:00",
                    afd  : "2023-05-21 00:00:00",
                    acd  : "2023-05-21 00:00:00",
                    esttime : "1",
                    runtime : "0",
                    trepeat : "0",
                    cuspas : "win,ads,ebay",
                    category  : "",
                    phrase  : "",
                    pseudoStore  : "",
                    pseudoBrand  : "",
                    pseudoASIN  : "",
                    type  : "sell",
                    config  : "",
                    skills  : "1, 10, 20, 30, 40",
                    delDate  : ""
                }
            ]
        }
    }
);

testcases.push(
    {
        "name" : "bypass test",
        "skip" : true,
        "number" : "5000",
        "function" : "sum_est_run_time",
        "arguments" : [[{ config : {estRunTime: 1} }, { config : {estRunTime: 2} }, { config : {estRunTime: 3} }]],
        "expected" : {
            "task_groups" : 
                [
                    {
                        "eastern" : [],
                        "central" : [], 
                        "mountain" : [], 
                        "pacific" : [
                            {
                              bid : 3,
                              tz : "pacific",
                              bw_works : [
                              ],
                              other_works : [
                                  {
                                      mid : 3,
                                      name: "sell",
                                      todos : [],
                                      cuspas : "win,chrome,etsy",
                                      config : {
                                          estRunTime : 1
                                      },
                                      start_time : 1
                                  }
                              ],
                            }
                        ], 
                        "alaska" : [], 
                        "hawaii" : []
                    }
                ],
            "added_missions" : [
                {
                    mid : 3,
                    owner : "songc@yahoo.com",
                    botid : 3,
                    ticket : 0,
                    status : "Scheduled",
                    createon : "2023-05-21 00:00:00",
                    esd : "2023-05-21 00:00:00",
                    ecd  : "2023-05-21 00:00:00",
                    asd  : "2023-05-21 00:00:00",
                    abd  : "2023-05-21 00:00:00",
                    aad  : "2023-05-21 00:00:00",
                    afd  : "2023-05-21 00:00:00",
                    acd  : "2023-05-21 00:00:00",
                    esttime : "1",
                    runtime : "0",
                    trepeat : "0",
                    cuspas : "win,chrome,etsy",
                    category  : "",
                    phrase  : "",
                    pseudoStore  : "",
                    pseudoBrand  : "",
                    pseudoASIN  : "",
                    type  : "sell",
                    config  : "",
                    skills  : "2, 10, 20, 30, 40, 60, 70, 90",
                    delDate  : ""
                }
            ]
        }
    }
);

testcases.push(
    {
        "name" : "bypass test",
        "skip" : true,
        "number" : "6000",
        "function" : "sum_est_run_time",
        "arguments" : [[{ config : {estRunTime: 1} }, { config : {estRunTime: 2} }, { config : {estRunTime: 3} }]],
        "expected" : {
            "task_groups" : 
                [
                    {
                        "eastern" : [],
                        "central" : [], 
                        "mountain" : [], 
                        "pacific" : [
                            {
                              bid : 2,
                              tz : "pacific",
                              bw_works : [
                                  {
                                      mid : 2,
                                      name: "browse_search",
                                      todos : [],
                                      cuspas : "win,ads,amz",
                                      config : {
                                          estRunTime : 1, 
                                          searches : [
                                              {
                                                  type: "browse_search",
                                                  site: "amz",
                                                  os: "win",
                                                  app: "chrome",
                                                  entry_paths: { 
                                                        type:  "Search", 
                                                        words: ["yoga mats"],                                //why list of words here, because category->subcategory->subsubcategory...., need a list of words.
                                                  },
                                                  top_menu_item : "Sporting Goods",   // this is the anchor name of the top menu item as the entrance point, for example "Computers", could also be | separated due to ebay and etsy, top main menu has sub-menu....
                                                  prodlist_pages: [
                                                      {
                                                          flow_type: "down up down",
                                                          products: [
                                                              {
                                                                  selType: "bs",
                                                                  detailLvl: 2,
                                                                  purchase: []
                                                              }
                                                          ]
                                                      }
                                                  ],                                             // list of configurations for the # of product list pages to browse. min: 1, max: 3, only browse up to top 3 pages.
                                                  buy_cfg: null
                                                }
                                          ]
                                      },
                                      start_time : 0
                                  }
                              ],
                              other_works : [
                              ],
                            }, 
                            {
                              bid : 3,
                              tz : "pacific",
                              bw_works : [
                                  {
                                      mid : 3,
                                      name: "browse_search",
                                      todos : [],
                                      cuspas : "win,ads,amz",
                                      config : {
                                          estRunTime : 1, 
                                          searches : [
                                              {
                                                  type: "browse_search",
                                                  site: "amz",
                                                  os: "win",
                                                  app: "chrome",
                                                  entry_paths: { 
                                                        type:  "Search", 
                                                        words: ["volleyball "],                                //why list of words here, because category->subcategory->subsubcategory...., need a list of words.
                                                  },
                                                  top_menu_item : "Sporting Goods",   // this is the anchor name of the top menu item as the entrance point, for example "Computers", could also be | separated due to ebay and etsy, top main menu has sub-menu....
                                                  prodlist_pages: [
                                                      {
                                                          flow_type: "down up down",
                                                          products: [
                                                              {
                                                                  selType: "bs",
                                                                  detailLvl: 2,
                                                                  purchase: []
                                                              }
                                                          ]
                                                      }
                                                  ],                                             // list of configurations for the # of product list pages to browse. min: 1, max: 3, only browse up to top 3 pages.
                                                  buy_cfg: null
                                                }
                                          ]
                                      },
                                      start_time : 1
                                  }
                              ],
                              other_works : [
                              ],
                            }
                        ], 
                        "alaska" : [], 
                        "hawaii" : []
                    }
                ],
            "added_missions" : [
                {
                    mid : 2,
                    owner : "songc@yahoo.com",
                    botid : 2,
                    ticket : 0,
                    status : "Scheduled",
                    createon : "2023-05-21 00:00:00",
                    esd : "2023-05-21 00:00:00",
                    ecd  : "2023-05-21 00:00:00",
                    asd  : "2023-05-21 00:00:00",
                    abd  : "2023-05-21 00:00:00",
                    aad  : "2023-05-21 00:00:00",
                    afd  : "2023-05-21 00:00:00",
                    acd  : "2023-05-21 00:00:00",
                    esttime : "1",
                    runtime : "0",
                    trepeat : "0",
                    cuspas : "win,chrome,amz",
                    category  : "",
                    phrase  : "",
                    pseudoStore  : "ABC",
                    pseudoBrand  : "CDE",
                    pseudoASIN  : "12345",
                    type  : "browse_search",
                    config  : "",
                    skills  : "0",
                    delDate  : ""
                }, 
                {
                    mid : 3,
                    owner : "songc@yahoo.com",
                    botid : 3,
                    ticket : 0,
                    status : "Scheduled",
                    createon : "2023-05-21 00:00:00",
                    esd : "2023-05-21 00:00:00",
                    ecd  : "2023-05-21 00:00:00",
                    asd  : "2023-05-21 00:00:00",
                    abd  : "2023-05-21 00:00:00",
                    aad  : "2023-05-21 00:00:00",
                    afd  : "2023-05-21 00:00:00",
                    acd  : "2023-05-21 00:00:00",
                    esttime : "1",
                    runtime : "0",
                    trepeat : "0",
                    cuspas : "win,chrome,amz",
                    category  : "",
                    phrase  : "",
                    pseudoStore  : "ABC",
                    pseudoBrand  : "CDE",
                    pseudoASIN  : "12345",
                    type  : "browse_search",
                    config  : "",
                    skills  : "0",
                    delDate  : ""
                }
            ]
        }
    }
);


testcases.push(
    {
        "name" : "bypass test",
        "skip" : true,
        "number" : "7000",
        "function" : "sum_est_run_time",
        "arguments" : [[{ config : {estRunTime: 1} }, { config : {estRunTime: 2} }, { config : {estRunTime: 3} }]],
        "expected" : {
            "task_groups" : 
                [
                    {
                        "eastern" : [],
                        "central" : [], 
                        "mountain" : [], 
                        "pacific" : [
                            {
                              bid : 2,
                              tz : "pacific",
                              bw_works : [
                                  {
                                      mid : 2,
                                      name: "run_simple_loop",
                                      todos : [],
                                      cuspas : "win,ads,amz",
                                      config : { },
                                      start_time : 0
                                  }
                              ],
                              other_works : [
                              ],
                            }, 
                            {
                              bid : 3,
                              tz : "pacific",
                              bw_works : [
                                  {
                                      mid : 3,
                                      name: "run_simple_loop",
                                      todos : [],
                                      cuspas : "win,ads,amz",
                                      config : { },
                                      start_time : 1
                                  }
                              ],
                              other_works : [
                              ],
                            }
                        ], 
                        "alaska" : [], 
                        "hawaii" : []
                    }
                ],
            "added_missions" : [
                {
                    mid : 2,
                    owner : "songc@yahoo.com",
                    botid : 2,
                    ticket : 0,
                    status : "Scheduled",
                    createon : "2023-05-21 00:00:00",
                    esd : "2023-05-21 00:00:00",
                    ecd  : "2023-05-21 00:00:00",
                    asd  : "2023-05-21 00:00:00",
                    abd  : "2023-05-21 00:00:00",
                    aad  : "2023-05-21 00:00:00",
                    afd  : "2023-05-21 00:00:00",
                    acd  : "2023-05-21 00:00:00",
                    esttime : "1",
                    runtime : "0",
                    trepeat : "0",
                    cuspas : "win,chrome,amz",
                    category  : "",
                    phrase  : "",
                    pseudoStore  : "ABC",
                    pseudoBrand  : "CDE",
                    pseudoASIN  : "12345",
                    type  : "run_simple_loop",
                    config  : "",
                    skills  : "101",
                    delDate  : ""
                }, 
                {
                    mid : 3,
                    owner : "songc@yahoo.com",
                    botid : 3,
                    ticket : 0,
                    status : "Scheduled",
                    createon : "2023-05-21 00:00:00",
                    esd : "2023-05-21 00:00:00",
                    ecd  : "2023-05-21 00:00:00",
                    asd  : "2023-05-21 00:00:00",
                    abd  : "2023-05-21 00:00:00",
                    aad  : "2023-05-21 00:00:00",
                    afd  : "2023-05-21 00:00:00",
                    acd  : "2023-05-21 00:00:00",
                    esttime : "1",
                    runtime : "0",
                    trepeat : "0",
                    cuspas : "win,chrome,amz",
                    category  : "",
                    phrase  : "",
                    pseudoStore  : "ABC",
                    pseudoBrand  : "CDE",
                    pseudoASIN  : "12345",
                    type  : "run_simple_loop",
                    config  : "",
                    skills  : "101",
                    delDate  : ""
                }
            ]
        }
    }
);



module.exports = { 
    testcases,
    test_resp_string,
    test_add_bots_resp,
    test_add_missions_resp,
    test_add_skills_resp,
    test_get_schedule_resp
    
};