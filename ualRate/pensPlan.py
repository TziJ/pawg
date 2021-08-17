#!/usr/bin/env python3
from pensPop import pensPop, pensMort
from pensFund import pensFund
import plotly.express as px
import pandas as pd
import statistics as stats
import os


class pensPlan(object):
    def __init__(self, currentYear, volatility, employmentGrowth=1.0, discountRate=0.07,
                 funds=0.75, premiumRate=1.0, tables=None):

        self.currentYear = currentYear
        self.employ = employmentGrowth
        self.cr = 0
        self.payGo = 0
        self.totalPay = 0
        self.pr = premiumRate
        self.instability = 1
        self.r = 0

        self.discountRate = discountRate

        self.population = pensPop([], self.discountRate, tables)
        self.population.simulatePopulation()

        self.liability = round(self.population.calculateTotalLiability(), 2)

        self.fund = pensFund(funds * self.liability, self.currentYear, volatility)
        self.ual = round(self.liability - sum(self.fund.ledger[self.currentYear]), 2)
        self.assets = sum(self.fund.ledger[self.currentYear])

        self.growthRate = 0.0

    def annualReport(self):
        # show number of active and retired members
        self.population.printReport()

        # Show current liability
        print("Current Liability: $%s" % '{:,}'.format(round(self.liability, 2)))

        # Show assets
        self.fund.printReport()

        # Show total salary
        self.population.calculateTotalSalary()

        # UAL
        if self.ual > 0:
            print("Unfunded Liability: $%s (%s%%)" % ('{:,}'.format(round(self.ual, 2)),
                                                      round((self.ual / self.liability) * 100)))
        else:
            print("Unfunded Liability: $0")

    def advanceOneYear(self):
        self.currentYear += 1
        info = self.population.advanceOneYear()
        old_assets = self.assets

        # variable to record growth in active population after hiring new members.
        popGrowth = sum([m.status == 'active' for m in self.population.members])
        self.population.hireReplacements(info['replace'], self.employ)
        popGrowth = sum([m.status == 'active' for m in self.population.members]) - popGrowth

        ## Calculate the increment of the normal cost.
        newLiability = round(self.population.calculateTotalLiability(), 2)
        normalCost = (newLiability - self.liability)
        self.liability = newLiability
        self.totalPay = round(self.population.calculateTotalSalary(), 2)

        [r, A] = self.fund.addInvestmentEarnings()
        self.r = round(r*100, 2)
        contribution = self.pr * normalCost
        self.fund.addPremiums(contribution)
        self.payGo = round(self.fund.payBenefits(info['benefit']), 2)
        self.fund.updateLedger(self.currentYear)
        self.assets = sum(self.fund.ledger[self.currentYear])

        # instability represents proximity to hypothesised equilibrium.
        self.instability = (contribution + self.discountRate*self.liability) - (r*A + normalCost)

        # Calculate Contribution Rate.
        if popGrowth != 0:
            self.cr = (normalCost + self.payGo) / (self.totalPay * popGrowth)
        else:
            try:
                self.cr = (normalCost + self.payGo) / self.totalPay
            except ZeroDivisionError:
                self.cr = 0.0

        # Calculate new UAL and growth rate.
        newUAL = max((self.liability - self.assets - self.payGo), 0)
        try:
            self.growthRate = (newUAL - self.ual) * 100 / self.ual
        except ZeroDivisionError:
            if newUAL != 0:
                self.growthRate = newUAL * 100 / self.liability
            else:
                self.growthRate = 0.0
        self.growthRate = round(self.growthRate, 2)
        self.ual = newUAL

    def adjustEmployment(self, N):
        """Adjust employment up or down."""
        if N > 0:
            self.population.addNewMembers(N)
        else:
            self.population.layoffMembers(-N)


def runModel(volatility, employmentGrowth=1.0, discountRate=0.07, funds=0.75, premiums=1.0, years=40, saveFiles=False,
             filename="plotly_graph", tables=None):
    # Create Plan and dictionary to keep track of annual data
    d = {}
    p = pensPlan(2000, volatility, employmentGrowth, discountRate, funds, premiums, tables=tables)

    d["UAL"] = [p.ual]
    d["Assets"] = [p.assets]
    d["Liability"] = [p.liability]
    d["UAL Growth(%)"] = [round(p.growthRate, 2)]
    d["Active Members"] = [sum([m.status == 'active' for m in p.population.members])]
    d["Retired Members"] = [sum([m.status == 'retired' for m in p.population.members])]
    d["Avg. Service"] = [round(p.population.getAvgService())]
    d["Contribution Rate"] = [p.cr]
    d["payGo"] = [p.payGo]
    d["Total Salary"] = [p.totalPay]
    d["Instability"] = [round(p.instability)]
    d["Investment Returns(%)"] = [p.r]

    # Run model for several years, saving data along the way
    for year in range(years):
        p.advanceOneYear()
        d["UAL"].append(p.ual)
        d["Assets"].append(p.assets)
        d["Liability"].append(p.liability)
        d["UAL Growth(%)"].append(round(p.growthRate, 2))
        d["Active Members"].append(sum([m.status == 'active' for m in p.population.members]))
        d["Retired Members"].append(sum([m.status == 'retired' for m in p.population.members]))
        d["Avg. Service"].append(round(p.population.getAvgService()))
        d["Contribution Rate"].append(p.cr)
        d["payGo"].append(p.payGo)
        d["Total Salary"].append(p.totalPay)
        d["Instability"].append(round(p.instability))
        d["Investment Returns(%)"].append(p.r)

    # Stops here if you're not trying to save the data visualization.
    if not saveFiles:
        return d

    # Convert dictionary data into a DataFrame, used to create the graph.
    df = pd.DataFrame(data=d, index=range(2000, (2001 + years)))

    # Create the graph itself.
    fig = px.line(df)

    # Save graph as HTML file in the appropriate folder. If no such directory exists yet, create it.
    # HTML files can be opened to view interactive plotly visualization.
    folder = "eg=%s_dr=%s_f=%s" % (str(employmentGrowth), str(discountRate), str(funds))
    try:
        os.makedirs('Graphs/%s' % folder)
    except OSError as e:
        if e.errno != 17:
            raise

    count = 1
    temp = filename
    filename = "%s_%s" % (temp, str(count))
    directory = "Graphs/%s/%s.html" % (folder, filename)
    while os.path.exists(directory):
        count += 1
        filename = "%s_%s" % (temp, str(count))
        directory = "Graphs/%s/%s.html" % (folder, filename)

    csv_directory = "Graphs/%s/%s.csv" % (folder, filename)
    df.to_csv(csv_directory)
    fig.write_html(directory)

    return d


def getModelData(volatility,
                 employmentGrowth=1.0,
                 discountRate=0.07,
                 funds=0.75,
                 premiums=1.0,
                 size=50,
                 years=100,
                 saveAll=True,
                 filename="data_1",
                 tables=None):
    # Create directory for data visualization, if necessary.
    folder = "eg=%s_dr=%s_f=%s" % (str(employmentGrowth), str(discountRate), str(funds))
    if not os.path.exists('Graphs/%s' % folder):
        os.makedirs('Graphs/%s' % folder)

    # Determine appropriate filename for visualization of mean values
    if filename == "data_1":
        count = 2
        directory = "Graphs/%s/%s.html" % (folder, filename)
        while os.path.exists(directory):
            filename = "data_%s" % (str(count))
            directory = "Graphs/%s/%s.html" % (folder, filename)
            count += 1
    else:
        count = 1
        temp = filename
        filename = "%s_%s" % (temp, str(count))
        directory = "Graphs/%s/%s.html" % (folder, filename)
        while os.path.exists(directory):
            count += 1
            filename = "%s_%s" % (temp, str(count))
            directory = "Graphs/%s/%s.html" % (folder, filename)

    # If you wish to visualize the data of each individual model, in addition to the mean data...
    if saveAll:
        # Create a folder to hold individual model graphs, based on the mean data filename
        if not os.path.exists('Graphs/%s/%s' % (folder, filename)):
            os.makedirs('Graphs/%s/%s' % (folder, filename))

        # All individual model graphs will be named graph_1, graph_2, graph_3, etc. and placed within the above folder
        # (The numbers are added within the runModel() function.)
        subdir = "%s/model" % filename

    else:
        subdir = None

    # Create list to store the data from each run.
    model_data = []

    #Print for checking progress
    print("%s:" % filename)
    print("\tRunning models...")

    for i in range(size):
        # Run the model, then append the resulting dictionary to the list.
        # Set saveAll to True if you want to save individual run visualizations.

        try:
            model_data.append(
                runModel(volatility, employmentGrowth, discountRate, funds, premiums, years, saveFiles=saveAll,
                         filename=subdir, tables=tables))
        except:
            print("\nAn error occurred while running models.\n%s out of %s models completed." % (str(i), str(size)))
            raise

    print("\tcomplete! Averaging data...")

    # Find the mean values across all runs and visualize them, to see overall shape of the data w/ the given parameters.
    mean_data = {"UAL": [], "Assets": [], "Liability": [], "UAL Growth(%)": [], "Active Members": [],
                 "Retired Members": [], "Avg. Service": [], "Contribution Rate": [], "payGo": [],
                 "Total Salary": [], "Instability": [], "Investment Returns(%)": []}
    for i in range(years):
        for key in mean_data:
            m = [run[key][i] for run in model_data]
            if key == "Active Members" or key == "Retired Members" or key == "Avg. Service" or key == "Instability":
                mean = round(stats.mean(m))
            else:
                mean = round(stats.mean(m), 2)
            mean_data[key].append(mean)

    print("\tcomplete!")
    # Convert dictionary data into a DataFrame, used to create the graph.
    df = pd.DataFrame(data=mean_data, index=range(2000, (2000 + years)))
    csv_directory = "Graphs/%s/%s.csv" % (folder, filename)
    df.to_csv(csv_directory)

    # Create the graph and save it as HTML file in the appropriate folder.
    fig = px.line(df)
    fig.write_html(directory)
    # HTML files can be opened to view interactive plotly visualization.
    #print("Visualization saved at %s\nCSV file saved at %s" % (directory, csv_directory))

    return [mean_data, model_data]


def setupFolders():
    try:
        os.makedirs('Graphs')
    except OSError as e:
        if e.errno != 17:
            raise


if __name__ == "__main__":
    # Create directories for storing graphs, if necessary
    setupFolders()
    tables = [pensMort("F", "General").mortTable, pensMort("F", "Safety").mortTable,
              pensMort("M", "General").mortTable, pensMort("M", "Safety").mortTable]

    # Volatility values to be used throughout. List contains mean and std. deviation (in that order) for the three
    # investment channels in pensFund.
    # default vol = [0.04, 0.03, 0.02, 0.03, 0.04, 0.04]
    vol = [0.03, 0.0, 0.01, 0.0, 0.03, 0.0]
    # Employment growth rate
    # eg = 1.0
    # Discount rate
    dr = 0.07
    # Initial funding (as a fraction of initial liability)
    # f = 1.0
    # premiums contribution modifier
    # pr = 1.0
    # Number of iterations for getModelData()
    size = 25
    # Length of each individual model in years
    years = 100
    # filename for your test
    #name = ("M7S0_premiums=%s" % str(pr))

    print("Beginning premiumRate tests.\n")
    eg = 0.5
    while eg <= 1.5:
        f = 0.5
        while f <= 1.5:
            pr = 0.5
            print("[EG=%s, F=%s]" % (eg, f))
            while pr <= 1.5:
                name = ("M7S0_premiums=%s" % str(pr))
                getModelData(vol, eg, dr, f, pr, size=size, years=years, filename=name, tables=tables)
                pr += 0.5
            print()
            f += 0.5
        eg += 0.5
    print("\nFinished premiumRate tests!\n")
