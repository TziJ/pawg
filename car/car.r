library(tidyverse)

## Given a cash flow, find the interest rate that will allow the
## deposits to compound to a future value.  cashFlow is a tibble
## with a 'year' column and a 'flow' column.

source("newton.r")
source("mortality.r")

## Every year, premiums are collected for everyone.  Imagine a big
## matrix of premium payments, where each row represents a year of
## premiums (P) and pension payments (R), and each column is all the
## actives who will retire in a class.
##
## year
##   1   P11   P12   P13   P14   P15 ...
##   2   R21   P22   P23   P24   P25 ...
##   3   R31   R32   P33   P34   P35 ...
##   4   R41   R42   R43   P44   P45 ...
##   5   R51   R52   R53   R54   P55 ...
##   6     .     .     .     .    .  ...
##   7     .     .     .     .    .  ...
##   8     .     .     .     .    .  ...
##
## The "1" class (first column) retires at the end of year 1, so
## receives its pension benefits in year 2.  The 2 class retires at
## the end of year 2, and so on.  We refer to this below as the master
## cash flow matrix.
##
##

##### SYSTEM SPECIFIC DEFINITIONS

## These are specific to the pension plan in question.  Definitions
## should be overridden with definitions from the data in the
## appropriate valuation report.

## These functions (doIseparate and doIretire) give the probability of
## separation or retirement, given the age and service years of the
## employee.
doesMemberSeparate <- function(age, service, status, tier=1) {
    cat("Running default doesMemberSeparate.\n");

    ## If this is not currently an active employee, get out.
    if (status != "active") return(status);

    rates <- c(0.070, 0.045, 0.037, 0.030, 0.025,
               0.017, 0.017, 0.017, 0.017, 0.015,
               0.011, 0.007, 0.007, 0.007, 0.006,
               0.005, 0.005, 0.004, 0.004, 0.004);

    service <- min(service, 20);
    if (runif(1) < rates[service]) status <- "separated";

    return(status);
}

doesMemberRetire <- function(age, service, status, tier=1) {
    cat("Running default doesMemberRetire.\n");

    ## If already retired, get out.
    if ((status == "retired") | (status == "deceased") |
        (status == "disabled") ) return(status);

    ## The service years on input refer to years that have begun, but
    ## not necessarily completed.  We want completed years.  This is
    ## related to the model's approximation that events happen on the
    ## transition from one year to the next, as opposed to the real
    ## world, where events happen whenever they feel like it.
    completedYears <- service - 1;

    if ((age >= 62) && (completedYears >= 15)) {
        if ( ((age == 62) && (runif(1) > 0.4)) |
             (((age > 62) && (age < 70)) && (runif(1) > 0.5)) |
             (age >= 70) ) {
            status <- "retired";
        }
    } else if (completedYears >= 20) {
            rates <- c(0.14, 0.14, 0.07, 0.07, 0.07,
                       0.22, 0.26, 0.19, 0.32, 0.30,
                       0.30, 0.30, 0.55, 0.55, 1.00);

            completedYears <- min(completedYears, 34);
            ## Roll the dice.
            if (runif(1) < rates[completedYears - 19]) status <- "retired";
    }

    return(status);
}

doesMemberBecomeDisabled <- function(age, sex, service, status,
                                     mortClass="General", tier=1) {
    cat("Running default doesMemberBecomeDisabled.\n");

    ## If already retired or disabled, don't change anything and get out.
    if ((status == "retired") | (status == "deceased") |
        (status == "disabled") ) return(status);

    ## These are rates for ages 20-25, 25-30, 30-35, etc
    rates <- c(0.0003, 0.0003, 0.0004, 0.0009, 0.0017, 0.0017, 0.0043, 0.01);

    ## Select the appropriate rate.  This is a quicker way to choose
    ## among the options than a big if statement.
    irate <- min(length(rates), ceiling((age - 20)/5));

    ## Roll the dice.
    if (runif(1) < rates[irate]) status <- "disabled";

    return(status);
}


## Defines the function 'doesMemberDie' using the pubs 2010 mortality
## tables in the mortalityTables subdirectory.
source("mortality.r")

## The assumed salary increment, from the table of merit increases in
## each valuation report.  Tier refers to any kind of subdivision
## among the members.
projectSalaryDelta <- function(year, age, salary, service=1, tier=1) {
    cat("Running default projectSalaryDelta.\n");

    if (age < 25) {
        out <- 1.075;
    } else if ((age >= 25) && (age < 30)) {
        out <- 1.0735;
    } else if ((age >= 30) && (age < 35)) {
        out <- 1.0674;
    } else if ((age >= 35) && (age < 40)) {
        out <- 1.0556;
    } else if ((age >= 40) && (age < 45)) {
        out <- 1.0446;
    } else if ((age >= 45) && (age < 50)) {
        out <- 1.0374;
    } else if (age >= 50) {
        out <- 1.035;
    }

    return(out);
}

projectPension <- function(salaryHistory, tier=1) {
    cat("Running default projectPension.\n");

    startingPension <- max(salaryHistory$salary) * 0.55;
    cola <- 1.02;

    ## If this person never retired, send them away without a pension.
    if (!("retired" %in% salaryHistory$status))
        return(salaryHistory %>% mutate(pension = 0));

    retireYear <- as.numeric(salaryHistory %>%
                             filter(status=="retired") %>%
                             summarize(retireYear=min(year)));

    return(salaryHistory %>%
           mutate(pension = ifelse(status == "retired",
                                   startingPension * cola^(year - retireYear),
                                   0)));

}

## Accepts a salary history tibble and adds a column for the estimated
## premiums paid into the system for this employee for each year.
## (Combined employer and employee share.)
projectPremiums <- function(salaryHistory) {
    cat("Running default projectPremiums.\n");

    return(salaryHistory %>%
           mutate(premium = salary * .25))
}



## For a given year, uses an age, years of service, and salary
## history, to project a typical career forward to separation or
## retirement, and backward to the initial hire.  Returns a tibble
## with salary figures for each working year, and a status column for
## active, separated, or retired.
##
## Can also input a salaryHistory tibble, with year, age,
## service, (annual) salary, and status columns.  This is assumed to
## be a partial record, and the function will use the assumptions and
## mortality tables to fill out the career of this person.
projectCareer <- function(year=0, age=0, service=0, salary=0,
                          salaryHistory=NA, sex="M",
                          mortClass="General", tier=1,
                          verbose=FALSE) {

    ## Test if the salaryHistory data frame is empty.
    if (is.null(dim(salaryHistory))) {

        ## If so we just have a single year to project from.
        career <- projectCareerFromOneYear(year, age, service, salary,
                                           sex=sex, mortClass=mortClass,
                                           tier=tier, verbose=verbose);
    } else {

        ## We have a few years to project from.
        career <- projectCareerFromRecord(salaryHistory, sex=sex,
                                          mortClass=mortClass,
                                          tier=tier, verbose=verbose)
    }

    return(career);
}

## Given data from an individual year, use the salary increase
## assumptions to work backward to the year of hire.  We assume you
## are starting from an active year.
simulateCareerBackward <- function(year, age, service, salary,
                                   sex="M", status="active",
                                   mortClass="General",
                                   tier=1, verbose=FALSE) {

    salaries <- c(salary);
    ages <- c(age);
    services <- c(service);
    statuses <- c("active");
    fromData <- c(FALSE);
    years <- c(year);

    ## March backward to the year of initial hire.
    if (service > 1) {
        for (iyear in seq(from=year - 1, to=year - service + 1)) {
            ## cat("calculating for", iyear, "\n");
            ages <- c(ages, age - (year - iyear));
            services <- c(services, service - (year - iyear));
            salaries <-
                c(salaries,
                  tail(salaries, 1)/projectSalaryDelta(iyear,
                                                       age - (year - iyear),
                                                       salary,
                                                       service=service,
                                                       tier=tier));
            statuses <- c(statuses, "active");
            years <- c(years, iyear);
            fromData <- c(fromData, FALSE);
        }
    }

    ## That first year was probably not a complete year.  Roll some
    ## dice and pick a random fraction of the year.
    salaries[length(salaries)] <- runif(1) * salaries[length(salaries)];

    ## Reverse the data so the years are in forward order.  Leave off
    ## the last one because that's just the original (input) year.
    ord <- head(order(years), -1);

    return(tibble(year =    years[ord],
                  age =     ages[ord],
                  service = services[ord],
                  salary =  salaries[ord],
                  fromData    =  fromData[ord],
                  status =  statuses[ord]));
}

simulateCareerForward <- function(year, age, service, salary,
                                  sex="M", status="active",
                                  mortClass="General",
                                  tier=1, verbose=FALSE) {

    salaries <- c(salary);
    ages <- c(age);
    services <- c(service);
    statuses <- c(as.character(status));
    fromData <- c(TRUE);  ## The first year is from data, the rest are sims.
    years <- c(year);

    if (verbose) cat("\nIn", year, "--simulating career forward for--\n",
                     "age:", age, "service:", service, "salary:", salary,
                     "status:", status, "mortClass:", mortClass, "tier:", tier,
                     "\n");

    ## Now march forward through a simulated career.  Stop when you
    ## hit "deceased."
    currentStatus <- status;
    currentService <- service + 1;
    iyear <- year + 1;
    while((iyear < (year + (110 - age))) && (currentStatus != "deceased")) {

        testAge <- age - (year - iyear);

        if (verbose) cat (iyear, ": At age: ", testAge,
                          ", service: ", currentService,
                          ", start as: ", currentStatus, sep="");

        ## Test for transitions.
        currentStatus <-
            doesMemberDie(testAge, sex, currentStatus,
                          mortClass=mortClass, verbose=verbose);
        currentStatus <-
            doesMemberSeparate(testAge, currentService, currentStatus);

        currentStatus <-
            doesMemberRetire(testAge, currentService, currentStatus,
                             tier=tier, verbose=verbose);

        if (verbose) cat (", end as:", currentStatus, ".\n", sep="");

        salaries <-
            c(salaries,
              ifelse(currentStatus == "active",
                     tail(salaries, 1) * projectSalaryDelta(iyear,
                                                            age-(year-iyear),
                                                            salary,
                                                            service=service,
                                                            tier=tier),
                     0));
        ages <- c(ages, testAge);
        services <- c(services, currentService);
        statuses <- c(statuses, currentStatus);
        years <- c(years, iyear);
        fromData <- c(fromData, FALSE);

        if (currentStatus == "deceased") break;

        ## Add a service year if still active.  Note that the ending
        ## total of service years will be one year too large.  This is
        ## because we're dealing with integer years and the
        ## transitions happen *during* a year.
        if (currentStatus == "active") currentService <- currentService + 1;
        iyear <- iyear + 1;
    }

    return(tibble(year=years,
                  salary=salaries,
                  age=ages,
                  service=services,
                  fromData=fromData,
                  status=statuses));
}

## Given a few years of salary, project the rest of a member's career
## and life.  The salaryHistory arg is a tibble with year, salary,
## age, service, and status columns.
projectCareerFromRecord <- function(salaryHistory, sex="M",
                                    mortClass="General", tier=1,
                                    verbose=FALSE) {

    backward <- simulateCareerBackward(head(salaryHistory$year, 1),
                                       head(salaryHistory$age, 1),
                                       head(salaryHistory$service, 1),
                                       head(salaryHistory$salary, 1),
                                       sex=sex,
                                       status=head(as.character(salaryHistory$status), 1),
                                       mortClass=mortClass,
                                       tier=tier, verbose=verbose);

    forward <- simulateCareerForward(tail(salaryHistory$year, 1),
                                     tail(salaryHistory$age, 1),
                                     tail(salaryHistory$service, 1),
                                     tail(salaryHistory$salary, 1),
                                     sex=sex,
                                     status=tail(as.character(salaryHistory$status), 1),
                                     mortClass=mortClass,
                                     tier=tier, verbose=verbose);

    return(tibble(year=c(backward$year,
                         salaryHistory$year,
                         tail(forward$year, -1)),
                  age=c(backward$age,
                        salaryHistory$age,
                        tail(forward$age, -1)),
                  service=c(backward$service,
                            salaryHistory$service,
                            tail(forward$service, -1)),
                  salary=c(backward$salary,
                           salaryHistory$salary,
                           tail(forward$salary, -1)),
                  fromData=c(backward$fromData,
                             rep(TRUE, length(salaryHistory$salary)),
                             tail(forward$fromData, -1)),
                  premium = c(rep(0, length(backward$salary)),
                              salaryHistory$premium,
                              rep(0, length(forward$salary) - 1)),
                  status=factor(c(backward$status,
                                  as.character(salaryHistory$status),
                                  tail(forward$status, -1)))));
}


## Given a single year's record, project what a career might look
## like.  We assume that the status is 'active' for the given year.
projectCareerFromOneYear <- function(year, age, service, salary, sex="M",
                                     mortClass="General", tier=1,
                                     verbose=FALSE) {

    backward <- simulateCareerBackward(year, age, service, salary,
                                       sex=sex, status="active",
                                       mortClass=mortClass, tier=tier,
                                       verbose=verbose)

    forward <- simulateCareerForward(year, age, service, salary,
                                     sex=sex, status="active",
                                     mortClass=mortClass, tier=tier,
                                     verbose=verbose)

    return(tibble(year=c(backward$year, forward$year),
                  age=c(backward$age, forward$age),
                  service=c(backward$service, forward$service),
                  salary=c(backward$salary, forward$salary),
                  fromData=c(backward$fromData, forward$fromData),
                  premium=rep(0, length(backward$salary) +
                                 length(forward$salary)),
                  status=factor(c(backward$status, forward$status),
                                levels=c("active", "separated",
                                         "retired", "deceased"))));
}

## Here's an object for a member, initialized for some specific year.
## The inputs are ages and years of service because that's what is
## published in the pension report tables.  The mortClass arg
## references the mortality tables (General, Safety, Teacher) and the
## tier argument is a string that can be used in whatever way is
## appropriate to reflect different classes of retirement benefits and
## salaries among plan members.
member <- function(age=0, service=0, salary=0,
                   id="none", salaryHistory=NA,
                   currentYear=2018, birthYear=0,
                   hireYear=0, sepYear=0, retireYear=0,
                   sex="M", mortClass="General", tier=1,
                   status="active", note="", verbose=FALSE) {

    ## Set up the facts of this member's life.
    if (is.null(dim(salaryHistory))) {
        ## If all we have is the single year's information, work with
        ## that.

        if ((birthYear == 0) && (age != 0)) {
            birthYear <- currentYear - age;
        } else {
            age <- currentYear - birthYear ;
        }
        if (birthYear == currentYear)
            stop("Must specify an age or a birth year.\n");

        if (hireYear == 0) {
            hireYear <- currentYear - service;
        } else {
            service <- currentYear - hireYear;
        }

        ## Generate an entire career's worth of salary history from
        ## the single-year snapshot.
        salaryHistory <- projectCareer(year=currentYear, age=age,
                                       service=service, salary=salary,
                                       sex=sex, mortClass=mortClass,
                                       tier=tier, verbose=verbose);
    } else {
        ## If we're here, we already have some fraction of a member's
        ## salary history to work with.
        currentYear <- head(salaryHistory$year, 1);
        age <- head(salaryHistory$age, 1);
        service <- head(salaryHistory$service, 1);

        birthYear <- currentYear - age;
        hireYear <- currentYear - service;

        ## Generate the rest of a career's worth of salary history
        ## from the history we've been given.
        salaryHistory <- projectCareer(salaryHistory=salaryHistory, sex=sex,
                                       mortClass=mortClass, tier=tier,
                                       verbose=verbose);
    }

    ## Add the premiums paid into the system.
    salaryHistory <- projectPremiums(salaryHistory);

    ## If this member gets to retire, estimate pension.
    if ("retired" %in% salaryHistory$status) {
        salaryHistory <- projectPension(salaryHistory, tier);
        retireYear <- as.numeric(salaryHistory %>%
            filter(status=="retired") %>% summarize(retireYear=min(year)));
    } else {
        retireYear <- NA;
    }

    if ("separated" %in% salaryHistory$status) {
        sepYear <- as.numeric(salaryHistory %>%
            filter(status=="separated") %>% summarize(sepYear=min(year)));
    } else {
        sepYear <- NA;
    }

    ## Estimate CAR for this employee.
    if ("retired" %in% salaryHistory$status) {
        car <- findRate(salaryHistory %>% mutate(netFlow = premium - pension),
                        flowName="netFlow", verbose=verbose);
    } else {
        car <- NA;
    }

    ## If no ID was provided, generate a random six-hex-digit id number.
    if (id == "none") {
        id <- format(as.hexmode(round(runif(1) * 16777216)),width=6);
    }

    ## Return everything in a list.
    out <- list(id=id,
                birthYear=birthYear,
                hireYear=hireYear,
                sepYear=sepYear,
                retireYear=retireYear,
                sex=sex,
                mortClass=mortClass,
                tier=tier,
                car=car,
                note=note,
                salaryHistory=salaryHistory);
    attr(out, "class") <- "member";

    return(out);
}

#change this to format / print.
format.member <- function(m, ...) {
    out <- paste0("birthYear: ", m$birthYear,
                  ", deathYear: ", max(m$salaryHistory$year),
                  " sex: ", m$sex,
                  "\n     hireYear: ", m$hireYear,
                  ", sepYear: ", m$sepYear,
                  ", retireYear: ", m$retireYear,
                  "\n     mortality class: ", m$mortClass,
                  ", tier: ", m$tier);

    ## The last row of the salary history is always zero, and not so
    ## interesting.
    career <- m$salaryHistory %>%
        group_by(status) %>%
        summarize(startYear=first(year), startSalary=first(salary),
                  endYear=last(year), endSalary=last(salary)) %>%
        filter(status == "active");

    out <- paste0(out, "\n",
                  "     salaryHistory: (", career$startYear[1], ", ",
                  format(career$startSalary[1], digits=5, big.mark=","), ") ",
                  " -> (", career$endYear[1], ", ",
                  format(career$endSalary[1], digits=5, big.mark=","), ")");

    if (!is.na(m$retireYear)) {
        retirement <- m$salaryHistory %>%
            group_by(status) %>%
            summarize(startYear=first(year), startPension=first(pension),
                      endYear=last(year), endPension=last(pension)) %>%
            filter(status == "retired");
        out <- paste0(out, "\n",
                  "     pension:       (", retirement$startYear[1], ", ",
                  format(retirement$startPension[1], digits=5, big.mark=","), ") ",
                  " -> (", retirement$endYear[1], ", ",
                  format(retirement$endPension[1], digits=5, big.mark=","), ")");
    }

    if (m$note != "") {
        out <- paste0(out, "\n", "     note: ", m$note);
    }

    out <- paste0(out, "\n",
                  "     car: ", format(m$car, digits=4));

    return(out);
}

print.member <- function(m, ...) {
    cat("id: ", m$id, ", ", format(m), "\n", sep="");
}

## Defines a class of 'memberList' for convenience.
memberList <- function(members=c()) {
    out <- list();

    if (length(members) > 0) {
        for (m in members) {
            out[[m$id]] <- m;
        }
    }

    attr(out, "class") <- "memberList";
    return(out);
}


format.memberList <- function(ml, ...) {
    out <- "";
    for (member in ml) {
        out <- paste0(out, "[[", member$id, "]]\n     ",
                      format(member), "\n");
    }
    return(substr(out, 1, nchar(out) - 1));
}

print.memberList <- function(ml, ...) {
    cat(format(ml), "\n");
}

# Then a 'snapshot' function to create an employee matrix for a given
# year and from a series of those, we can create the 'P' matrix above.



## Generate N new active employees with the given ranges, and append
## them to the input list of members.
genEmployees <- function (N=1, ageRange=c(20,25), servRange=c(0,5),
                         avgSalary=75000, members=memberList(),
                         class="General", status="active") {

    ages <- round(runif(N)*(ageRange[2] - ageRange[1])) + ageRange[1];
    servs <- round(runif(N)*(servRange[2] - servRange[1])) + servRange[1];
    salaries <- rnorm(N, mean=avgSalary, sd=5000);

    for (i in 1:N) {
        m <- member(age=ages[i], service=servs[i], salary=salaries[i]);
        members[[m$id]] <- m;
    }

    return(members);
}

## Make a tibble from a memberList.  The sampler is a function that
## takes a member object and returns TRUE or FALSE whether it should
## be included in the output tibble.
##
## e.g. function(m) { ifelse(m$tier == 1, TRUE, FALSE) }
##
makeTbl <- function(memberList, sampler=function(m) {TRUE} ) {

    out <- tibble();

    for (member in memberList) {
        if (sampler(member))
            out <- rbind(out,
                         tibble(id=c(member$id),
                                hireYear=c(member$hireYear),
                                sepYear=c(member$sepYear),
                                retireYear=c(member$retireYear),
                                maxSalary=c(max(member$salaryHistory$salary)),
                                car=c(member$car),
                                tier=c(member$tier),
                                birthYear=c(member$birthYear),
                                deathYear=c(max(member$salaryHistory$year))));
    }

    return(out);
}

## Build the master cash flow matrix.  This involves grouping retirees
## by retirement date and aggregating them.
buildMasterCashFlow <- function(memberTbl, members, verbose=FALSE) {

    ## Our master cash flow will begin at the earliest hire date and
    ## end at the latest death date.
    startYear <- min(memberTbl$hireYear);
    endYear <- max(memberTbl$deathYear);

    ## Get all the retireYears, in order.
    retireYears <- unique(memberTbl$retireYear)
    retireYears <- retireYears[order(retireYears, na.last=NA)];

    ## Initialize output tbl.
    out <- tibble(year=startYear:endYear);
    nYears <- endYear - startYear + 1;

    if (verbose) cat("Starting at", startYear, "ending at", endYear,
                     "n =", nYears, "\n");

    ## Loop through all the potential retirement classes, even if
    ## they're empty.
    for (retireClass in min(retireYears):max(retireYears)) {

        if (verbose) cat("Considering retirement class", retireClass, "\n");

        ## Initialize an empty row to hold the cash flow from this class.
        collectiveCashFlow <- rep(0, nYears);

        if (retireClass %in% retireYears) {

            classMemberIDs <- memberTbl %>%
                filter(retireYear == retireClass) %>%
                select(id);

            if (verbose) print(classMemberIDs);

            ## Now add the cash flow from each member of that retirement
            ## class to the collective cash flow.
            for (id in classMemberIDs$id) {
                if (verbose) cat("adding", id, format(members[[id]]), "\n");

                for (iyear in members[[id]]$salaryHistory$year) {
                    yearsFlow <- as.numeric(members[[id]]$salaryHistory %>%
                        filter(year == iyear) %>%
                        mutate(flow = premium - pension) %>%
                        select(flow));
                    collectiveCashFlow[1 + iyear - startYear] <-
                        collectiveCashFlow[1 + iyear - startYear] + yearsFlow;
                }
            }
        }

        ## Add the column for this class.
        out <- cbind(out, tibble(flow=collectiveCashFlow) %>%
                          rename_with(function(x) {
                              ifelse(x=="flow",
                                     paste0('R',retireClass), x)}));
    }

    out <- out %>% mutate(sum=rowSums(across(where(is.double)))) ;

    return(tibble(out));
}


## Given a function to construct a model population of plan members,
## this function will run that model and compute the CAR for its members.
runModelOnce <- function(modelConstructionFunction,
                         sampler=function(m) {TRUE},
                         verbose=FALSE) {

    model <- modelConstructionFunction(verbose=verbose);

    if (verbose) cat("model: Constructed a model with", length(model),
                     "members.\n");

    ## Make a summary table of all the members.
    modelTbl <- makeTbl(model, sampler=sampler);

    ## Build the master cash flow matrix.
    modelMCF <- buildMasterCashFlow(modelTbl, model, verbose=verbose);

    if (verbose) cat("model: Retirement classes:", dim(modelMCF)[2] - 2,
                     "from", colnames(modelMCF)[2],
                     "to", head(tail(colnames(modelMCF),2),1), "\n");

    ## Compute the CAR for the overall results.
    modelCAR <- findRate(modelMCF, flowName="sum", verbose=verbose);

    if (verbose) cat("model: CAR estimate:", modelCAR, "\n");

    ## Record the aggregate CAR under the year 1000 because why not.
    modelOut <- tibble(ryear = c(1000),
                       car = c(modelCAR - 1.0));

    ## We are also interested in calculating the CAR for each
    ## retirement class. Note that there are two extra columns in the
    ## master cash flow matrix, for the year and for the row sums.  So
    ## subtract two to get the number of retirement classes.
    minRetireYear <- min(modelTbl$retireYear, na.rm=TRUE);
    for (i in 1:(dim(modelMCF)[2] - 2)) {
        newYear <- minRetireYear + i - 1;
        newRate <- findRate(modelMCF, flowName=paste0("R", newYear));

        ## If no error, record the rate for this retirement class.
        if (newRate != 1.0) {
            modelOut <- rbind(modelOut,
                              tibble(ryear=c(newYear), car=c(newRate - 1.0)));
        }
    }

    return(list(model=model,
                modelTbl=modelTbl,
                modelMCF=modelMCF,
                modelOut=modelOut));
}

runModel <- function(modelConstructionFunction, N=1,
                     sampler=function(m) {TRUE},
                     verbose=FALSE) {
    if (verbose) cat("Starting run on:", date(),"\n");

    ## Prepare the output, just a record of years and CAR estimates.
    modelOut <- tibble(ryear=c(), car=c());

    for (i in 1:N) {
        if (verbose) cat("  ", date(), ": model run number", i, "...");

        M <- runModelOnce(modelConstructionFunction, sampler=sampler,
                          verbose=verbose)

        modelOut <- rbind(modelOut, M$modelOut);

        if (verbose) cat("runModel: CAR =",
                         as.numeric(M$modelOut %>%
                                    filter(ryear == 1000) %>%
                                    select(car)), "\n");
    }

    if (verbose) cat("Ending run on:", date(),"\n");

    return(modelOut);
}


## Some useful output routines.
library(ggplot2)

plotModelOut <- function(modelOut) {

    modelOutSummary <-
        modelOut %>%
        group_by(ryear) %>%
        summarize(car=mean(car));

    modelOutAvg <- modelOutSummary %>%
        filter(ryear == 1000) %>% select(car) %>% as.numeric();

    plotOut <- ggplot(modelOutSummary %>% filter(ryear > 1900)) +
        geom_point(aes(x=ryear, y=car), color="blue") +
        ylim(c(0,.1)) +
        geom_hline(yintercept=modelOutAvg, color="red") +
        labs(x="retirement class", y="CAR");

    return(plotOut);
}



