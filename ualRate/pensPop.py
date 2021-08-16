#!/usr/bin/env python3
import random
from collections import deque
import numpy as np
import pandas as pd
import openpyxl
from pathlib import Path
from copy import deepcopy
from matplotlib import pyplot as plt


class pensMort:
    def __init__(self, sex, mortalityClass):
        self.sex = sex
        self.mortalityClass = mortalityClass

        ## ET: import mortality table
        m_file = Path("..", "mortalityTables", "pub-2010-headcount-mort-rates.xlsx")
        m_wb = openpyxl.load_workbook(m_file)
        pubG = m_wb["PubG.H-2010"]

        if self.mortalityClass == "General":
            pubG = m_wb["PubG.H-2010"]

        if self.mortalityClass == "Safety":
            pubG = m_wb["PubS.H-2010"]

        ## ET: convert excel into a dataframe
        df_pubG = pd.DataFrame(pubG.values)
        ## ET: clean data frame (i.e. remove extra empty columns, reset index)
        df_pubG = df_pubG.drop(df_pubG.index[range(3)])
        df_pubG = df_pubG.drop(labels=[0, 2], axis=1).reset_index()

        self.data = df_pubG
        self.mortTable = self.getMortalityTables()
        m_wb.close()

    def getMortalityTables(self):
        ## ET: convert data frame into dictionary
        ## index: age (number)
        ## key: mortality rate of employee(0 position), healthy retiree(1), disabled retiree(2), contingent survivor(3)(list of numbers)
        ## split into two dictionaries, one for female, one for male

        temp = {}
        if self.sex == "F":
            df_pubG = self.data.drop(self.data.iloc[:, 6:20], axis=1)
            df_pubG = df_pubG.rename(columns=df_pubG.iloc[1])

            df_pubG[
                ["Healthy Retiree", "Disabled Retiree", "Contingent Survivor"]
            ] = df_pubG[
                ["Healthy Retiree", "Disabled Retiree", "Contingent Survivor"]
            ].fillna(
                value=0
            )

            for index, row in df_pubG.iterrows():
                temp[row["Age"]] = [
                    row["Employee"],
                    row["Healthy Retiree"],
                    row["Disabled Retiree"],
                    row["Contingent Survivor"],
                ]
            return temp

        elif self.sex == "M":
            df_pubG = self.data.iloc[:, np.r_[1, 7:11]].reset_index()
            df_pubG = df_pubG.rename(columns=df_pubG.iloc[1])
            df_pubG[
                ["Healthy Retiree", "Disabled Retiree", "Contingent Survivor"]
            ] = df_pubG[
                ["Healthy Retiree", "Disabled Retiree", "Contingent Survivor"]
            ].fillna(
                value=0
            )
            for index, row in df_pubG.iterrows():
                temp[row["Age"]] = [
                    row["Employee"],
                    row["Healthy Retiree"],
                    row["Disabled Retiree"],
                    row["Contingent Survivor"],
                ]
            return temp


class pensMember(object):
    def __init__(
            self,
            age,
            sex,
            service,
            salary,
            currentYear,
            mortalityClass="General",
            tier="1",
            status="active",
            id="*",
            tables=None
    ):
        self.age = age
        self.tables = tables
        self.sex = sex
        self.salary = salary
        self.mortalityClass = mortalityClass
        self.tier = tier
        self.service = service
        self.status = status
        self.id = id
        self.currentYear = currentYear
        self.birthYear = currentYear - age
        self.retireYear = 0
        self.hireYear = currentYear - service
        self.pension = self.salary * 0.55
        self.cola = 1.025  # inflation, set to 1 to neutralize
        self.mortDict = 0
        self.yearSalaryDict = {}
        self.salaryHistory = deque([salary])
        self.simulateCareerBackward()
        self.getMortTable()

        if self.id == "*":
            self.id = "%0.6x" % random.randint(1, pow(16, 6))

    def simulateCareerBackward(self):
        """Takes the current salary and service and projects a salary
        history backwards using the salaryGrowth value."""

        year = self.currentYear

        if self.service > 1:
            for iyear in range(
                    self.currentYear - 1, self.currentYear - self.service, -1
            ):
                self.yearSalaryDict[year] = (
                        self.salaryHistory[0] / self.projectSalaryDelta()
                )
                year = year - 1

        ## That first year was probably not a complete year.  Roll
        ## some dice and pick a random fraction of the year.
        self.salaryHistory[0] = random.random() * self.salaryHistory[0]

    def projectSalaryDelta(self):
        """Uses the age, service, and tier to project the change in pay
        between one year and the next."""

        ## These are typical values scrounged from a valuation report
        ## for a fire department in Arizona.  (For which service and
        ## tier are not relevant.)
        if self.age < 25:
            out = 1.075
        elif self.age >= 25 and self.age < 30:
            out = 1.0735
        elif self.age >= 30 and self.age < 35:
            out = 1.0674
        elif self.age >= 35 and self.age < 40:
            out = 1.0556
        elif self.age >= 40 and self.age < 45:
            out = 1.0446
        elif self.age >= 45 and self.age < 50:
            out = 1.0374
        elif self.age >= 50:
            out = 1.035

        # out -= 0.035 #to set inflation to 0

        return out

    def applyPensionCOLA(self):
        self.pension *= self.cola

    def doesMemberSeparate(self):
        """TBD: Does member leave employment?"""
        if self.status != "active":
            return False
        rates = [
            0.070,
            0.045,
            0.037,
            0.030,
            0.025,
            0.017,
            0.017,
            0.017,
            0.017,
            0.015,
            0.011,
            0.007,
            0.007,
            0.007,
            0.006,
            0.005,
            0.005,
            0.004,
            0.004,
            0.004,
        ]

        service = min(self.service, 20)
        if random.random() < rates[service - 1]:
            return True
        else:
            return False

    def doesMemberRetire(self):
        """TBD: What it sounds like"""
        if (
                self.status == "retired"
                or self.status == "deceased"
                or self.status == "disabled"
        ):
            return False

        if self.age >= 62 and self.service >= 15:
            if (
                    (self.age == 62 and random.random() > 0.4)
                    or (self.age > 62 and self.age < 70 and random.random() > 0.5)
                    or (self.age >= 70)
            ):
                return True
            elif self.service >= 20:
                rates = [
                    0.14,
                    0.14,
                    0.07,
                    0.07,
                    0.07,
                    0.22,
                    0.26,
                    0.19,
                    0.32,
                    0.30,
                    0.30,
                    0.30,
                    0.55,
                    0.55,
                    1.00,
                ]
                service = min(self.service, 34)
                if random.random() < rates[service - 20]:
                    return True
        return False

    def getMortTable(self):
        """determine with mortality dictionary to use based on pensMember sex and mortality class"""
        if self.tables is None:
            if self.sex == "F":
                if self.mortalityClass == "General":
                    self.mortDict = pensMort("F", "General").mortTable
                if self.mortalityClass == "Safety":
                    self.mortDict = pensMort("F", "Safety").mortTable

            elif self.sex == "M":
                if self.mortalityClass == "General":
                    self.mortDict = pensMort("M", "General").mortTable
                if self.mortalityClass == "Safety":
                    self.mortDict = pensMort("M", "Safety").mortTable
        else:
            index = 0
            if self.sex == "M":
                index += 2
            if self.mortalityClass == "Safety":
                index += 1
            self.mortDict = self.tables[index]

    def doesMemberDie(self):
        """TBD: Check if member dies"""

        if self.status == "active":
            if random.random() < self.mortDict[self.age][0]:
                return True

        ## ET: Assuming every retiree is healthy for now
        elif self.status == "retired":
            if random.random() < self.mortDict[self.age][1]:
                return True
        elif self.status == "deceased":
            return True

    def ageOneYear(self):
        """TBD: Age a year, get a raise, decide whether to separate or retire.
        Maybe die.  Change status and salary accordingly."""

        # Should members' salary and service increase before or after separation/retire checks?
        # If a person retires, should their service and salary not increase for that year? Or would it increase for the year and then stop?

        ## ET: Check for a change of status, then adjust the salary if
        ## it's still relevant.

        self.currentYear += 1

        if self.status != "deceased":
            self.age += 1

        if self.status == "active":
            self.service += 1
            self.salary *= self.projectSalaryDelta()
            self.yearSalaryDict[self.currentYear] = self.salary
            self.pension = self.yearSalaryDict[self.currentYear] * 0.55

            if self.doesMemberSeparate():
                self.status = "separated"
                self.salary = 0
            elif self.doesMemberRetire():
                self.status = "retired"
                self.retireYear = self.currentYear
                self.salary = 0

        if self.doesMemberDie():
            self.status = "deceased"
            self.salary = 0

    def print(self):
        print(
            "Member %s: Age: %.0f, Sex: %s, Class: %s, Tier, %s"
            % (self.id, self.age, self.sex, self.mortalityClass, self.tier)
        )
        print(
            "BirthYear: %.0f, HireYear: %.0f, Service: %.0f, RetireYear: %.0f"
            % (self.birthYear, self.hireYear, self.service, self.retireYear)
        )
        print("Current Year: %.0f, Salary: %.0f, " % (self.currentYear, self.salary))


#        self.pension = 0
#        self.cola = 1.025
#        self.discountrate = 1.07
#        self.mortDict = 0
#        self.salaryHistory = deque([salary])
#        self.simulateCareerBackward()
#        self.getMortSex()


class pensPop(object):
    def __init__(self, members=[], discountRate=0.07, tables=None):
        # A list of member objects.
        self.members = members
        self.startingSalary = 50000
        self.avgAge = 30
        self.sampleSize = 100
        self.simulatePopulation()
        self.discount = 1 + discountRate
        self.tables = tables

    def simulateMembers(
            self,
            N,
            ageRange,
            serviceRange,
            avgSalary,
            sex="*",
            mortalityClass="General",
            tier="1",
            status="active",
    ):
        """Generates N member objects with randomly distributed ages and
        services.  Sex is random, too, unless it's specified."""
        out = []
        for i in range(0, int(N)):
            if sex == "*":
                if random.random() > 0.5:
                    chosenSex = "M"
                else:
                    chosenSex = "F"
            else:
                chosenSex = sex

            out.append(
                pensMember(
                    random.randint(ageRange[0], ageRange[1]),
                    chosenSex,
                    random.randint(serviceRange[0], serviceRange[1]),
                    np.random.normal(avgSalary, avgSalary / 15),
                    2021,
                    mortalityClass=mortalityClass,
                    tier=tier,
                    status=status,
                    tables=self.tables
                )
            )

        return out

    def estimateSalary(self, serviceYears):
        """Estimates a starting salary in 2020 dollars."""

        if serviceYears <= 15:
            salary = 51000 + serviceYears * 1600 + np.random.normal(0, 2500)
        elif serviceYears <= 25:
            salary = (
                    self.estimateSalary(15)
                    + (serviceYears - 15) * 800
                    + np.random.normal(0, 2500)
            )
        else:
            salary = self.estimateSalary(25) + (serviceYears - 25) * np.random.normal(
                500, 100
            )
        return salary

    def simulatePopulation(self):
        """Generates a collection of plan members.  This can be taken from
        the table of population demographics in any valuation report."""

        m_file = Path("..", "ageServiceTables", "age-service-distribution.xlsx")
        m_wb = openpyxl.load_workbook(m_file, data_only=True)
        asd = m_wb["Cal-T"]
        m_wb.close()
        df_asd = pd.DataFrame(asd.values)
        df_asd = df_asd.rename(columns=df_asd.iloc[0])
        df_asd = df_asd.set_index("age")
        total = df_asd["total"]["total"]
        total_retired = 270835
        df_asd = df_asd.drop(index=["age", "total"], columns=["total"])
        df_asd = df_asd.applymap(lambda x: x / total)

        for index, row in df_asd.iterrows():
            ageR = index.split(",")
            self.members.extend(
                self.simulateMembers(
                    round(self.sampleSize * row[0]),
                    ageRange=(int(ageR[0]), int(ageR[1])),
                    serviceRange=(0, 1),
                    avgSalary=self.estimateSalary(1),
                )
            )

            self.members.extend(
                self.simulateMembers(
                    round(self.sampleSize * row[1]),
                    ageRange=(int(ageR[0]), int(ageR[1])),
                    serviceRange=(2, 4),
                    avgSalary=self.estimateSalary(3),
                )
            )

            self.members.extend(
                self.simulateMembers(
                    round(self.sampleSize * row[2]),
                    ageRange=(int(ageR[0]), int(ageR[1])),
                    serviceRange=(5, 9),
                    avgSalary=self.estimateSalary(7),
                )
            )

            self.members.extend(
                self.simulateMembers(
                    round(self.sampleSize * row[3]),
                    ageRange=(int(ageR[0]), int(ageR[1])),
                    serviceRange=(10, 14),
                    avgSalary=self.estimateSalary(12),
                )
            )

            self.members.extend(
                self.simulateMembers(
                    round(self.sampleSize * row[4]),
                    ageRange=(int(ageR[0]), int(ageR[1])),
                    serviceRange=(15, 19),
                    avgSalary=self.estimateSalary(17),
                )
            )

            self.members.extend(
                self.simulateMembers(
                    round(self.sampleSize * row[5]),
                    ageRange=(int(ageR[0]), int(ageR[1])),
                    serviceRange=(20, 24),
                    avgSalary=self.estimateSalary(22),
                )
            )

            self.members.extend(
                self.simulateMembers(
                    round(self.sampleSize * row[6]),
                    ageRange=(int(ageR[0]), int(ageR[1])),
                    serviceRange=(25, 29),
                    avgSalary=self.estimateSalary(27),
                )
            )

            self.members.extend(
                self.simulateMembers(
                    round(self.sampleSize * row[7]),
                    ageRange=(int(ageR[0]), int(ageR[1])),
                    serviceRange=(30, 34),
                    avgSalary=self.estimateSalary(32),
                )
            )

            self.members.extend(
                self.simulateMembers(
                    round(self.sampleSize * row[8]),
                    ageRange=(int(ageR[0]), int(ageR[1])),
                    serviceRange=(35, 39),
                    avgSalary=self.estimateSalary(37),
                )
            )

            self.members.extend(
                self.simulateMembers(
                    round(self.sampleSize * row[9]),
                    ageRange=(int(ageR[0]), int(ageR[1])),
                    serviceRange=(40, 44),
                    avgSalary=self.estimateSalary(42),
                )
            )

            self.members.extend(
                self.simulateMembers(
                    round(self.sampleSize * row[10]),
                    ageRange=(int(ageR[0]), int(ageR[1])),
                    serviceRange=(45, 60),
                    avgSalary=self.estimateSalary(47),
                )
            )

            ## retired members
        s = np.random.normal(4000, 4000)
        if s < 2000:
            s = random.uniform(2000, 4000)

        age_lower = 60
        age_upper = 65

        for i in range(10):
            self.members.extend(
                self.simulateMembers(
                    round(
                        self.sampleSize
                        * ((total_retired / (total + total_retired)) * (0.5 ** i))
                        * 0.1
                    ),
                    ## change 0.93 if you want to change the mortality rate of the reitred population
                    ageRange=(age_lower, age_upper),
                    serviceRange=(25, 30),
                    avgSalary=s,
                    status="retired",
                )
            )

            age_lower += 5
            age_upper += 5

        ## data source: California State Teacher's Retiremenet System (p.75-76)
        ## https://www.calstrs.com/sites/main/files/file-attachments/db-valuation-2019.pdf

    def advanceOneYear(self):
        """TBD: Advance the population by a year -- increase everyone's age
        and service, give them raises, retire some people, others die,
        or separate. """
        retirementBenefit = 0
        replacements = 0
        for member in self.members:
            wasActive = False
            if member.status == "active":
                wasActive = True
            member.ageOneYear()
            if member.status == "retired":
                retirementBenefit += member.pension
                if wasActive:
                    replacements += 1
            elif member.status != "active" and wasActive:
                replacements += 1

        return {"benefit": retirementBenefit, "replace": replacements}

    def hireReplacements(self, N, pct=1.0):
        """TBD: Replace retired and separated workers to maintain headcount.
        If pct is less than one, only replace that proportion of the retired
        and separated."""
        self.members.extend(
            self.simulateMembers(
                int(N * pct),
                ageRange=(self.avgAge - 5, self.avgAge + 5),
                serviceRange=(0, 1),
                avgSalary=self.startingSalary,
            )
        )

    def addNewMembers(
            self,
            N,
            ageRange,
            serviceRange,
            avgSalary,
            sex="*",
            mortalityClass="General",
            tier="1",
    ):
        """TBD: New hires who aren't replacements."""

        self.members.extend(
            self.simulateMembers(
                N,
                ageRange=(25, 35),
                serviceRange=(0, 5),
                avgSalary=self.estimateSalary(2),
            )
        )

    def layoffMembers(self, N):
        """TBD: Remove given number of members.  Favor removal of the
        younger members."""

        for i in range(N):
            for m in self.members:
                if m.age >= 20 and m.age <= 25:
                    self.members.remove(m)

    def printReport(self):
        print(
            "N: %.0f members, %0.f active, %0.f retired, %0.f separated, %0.f deceased"
            % (
                len(self.members),
                sum([m.status == "active" for m in self.members]),
                sum([m.status == "retired" for m in self.members]),
                sum([m.status == "separated" for m in self.members]),
                sum([m.status == "deceased" for m in self.members]),
            )
        )
        sal = sum([m.salary for m in self.members]) / len(self.members)
        print("Average salary: $%s" % "{:,}".format(round(sal, 2)))

    def calculateLiability(self, member, discountrate, cola):
        """TBD: Estimate accrued liability for this member."""

        ## Step 1: if person is active, estimate year of retirement
        ## ET: created a deep copy of the member so not to effect the actual member's attribute
        ## when generating annual report
        simulateMemberLife = deepcopy(member)

        yearsUntilRetirement = 0
        if simulateMemberLife.status == "active":
            while simulateMemberLife.status == "active":
                simulateMemberLife.ageOneYear()
                yearsUntilRetirement += 1

        ## Step 2: Estimate how many years of retirement this person
        ## is likely to enjoy. (Or how many years left, for members
        ## who are already retired.)

        yearsOfRetirement = 0
        if simulateMemberLife.status == "retired":
            while simulateMemberLife.status != "deceased":
                yearsOfRetirement += 1
                simulateMemberLife.ageOneYear()

        liabilityPresentValue = 0
        for i in range(yearsUntilRetirement + yearsOfRetirement):
            ## Step 3: estimate retirement benefit earned
            liability = member.pension * cola ** (i - 1)

            ## Step 4: Apply the discount rate for each of the years to
            ## get the present value in the current year.
            liabilityPresentValue = liabilityPresentValue + (liability) / (
                    discountrate ** i
            )
        return liabilityPresentValue

    def calculateTotalLiability(self):
        """Calculate the present value of the liability, aka normal cost, for all the
            members."""

        sum = 0
        for m in self.members:
            sum += self.calculateLiability(m, self.discount, 1.02)
        return sum

    def calculateTotalSalary(self):
        total_salary = 0
        for m in self.members:
            total_salary += m.salary
        return total_salary

    def getAnnualReport(self):

        """generate annual report with total members and total normal cost"""
        report = []

        for i in range(20):
            for m in self.members:
                if self.doesMemberDie():
                    self.members.remove(m)

            report.append([len(self.members), self.calculateTotalLiability()])
            self.advanceOneYear()
        return report

    def getAvgService(self):
        sum = 0
        count = 0
        for m in self.members:
            if m.status == "active":
                count += 1
                sum += m.service
        if count == 0:
            return 0
        return sum / count


##################### TESTING FUNCTIONS ######################


if __name__ == "__main__":

    def testdoesMemberRetire():
        counter = 0
        andy = pensMember(62, "M", 15, 1000, 2005)
        for i in range(100000):
            if andy.doesMemberRetire():
                counter += 1
        print(counter)  ## ET: should be around 60000


    def testdoesMemberSeparate():
        counter = 0
        for i in range(100000):
            andy = pensMember(62, "M", 15, 1000, 2005)
            if andy.doesMemberSeparate():
                counter += 1
        print(counter)  ## ET: should be around 600


    def testdoesMemberDie():
        counter = 0
        andy = pensMember(18, "M", 15, 1000, 2005)
        for i in range(100000):
            if andy.doesMemberDie():
                counter += 1
        print(counter)  ## ET: should be around 30


    def testcalculateLiability():
        x = pensPop()
        andy = pensMember(20, "M", 15, 1000, 2005)
        print(x.calculateLiability(andy))
        print(andy.pension)
        andy.ageOneYear()
        print(x.calculateLiability(andy))


    def testcalculateTotalLiability():
        x = pensPop()
        x.advanceOneYear()
        print(x.calculateTotalLiability())


    def testgetAnnualReport():
        x = pensPop()
        print(x.getAnnualReport())


    def testAgeOneYear():
        m1 = pensMember(20, "M", 2, 500, 2010)
        m2 = pensMember(30, "F", 2, 500, 2010)
        m3 = pensMember(50, "M", 2, 500, 2010)

        m1_ageOneYear = m1.ageOneYear()
        m2_ageOneYear = m2.ageOneYear()
        m3_ageOneYear = m3.ageOneYear()
        print(m1_ageOneYear.currentYear)
        print(m2_ageOneYear.age)
        print(m3_ageOneYear.service)


    def testAdvanceOneYear():
        x = pensPop()
        for i in range(10):
            print(x.advanceOneYear())


    def testSimulatePopulation():
        total_retired = 270835
        x = pensPop()
        counter = []

        age_lower = 20
        age_upper = 25

        for i in range(15):
            y = 0
            for m in x.members:
                if m.age <= age_upper and m.age >= age_lower:
                    y += 1
            counter.append(y)

            age_lower += 5
            age_upper += 5

        plt.plot(counter)
        plt.show()


    def testCalculateTotalSalary():
        x = pensPop()
        print(x.calculateTotalSalary())


    # testdoesMemberRetire()
    # testcalculateLiability()
    # testgetAnnualReport()
    # testdoesMemberDie()
    # testAgeOneYear()
    # testcalculateTotalLiability()
    # testCalculateTotalSalary()
    #testSimulatePopulation()
    # testSimulatePopulation()
    # testAdvanceOneYear()
