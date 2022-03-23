import os
import re
from urllib.parse import urlencode

import numpy as np
import plotly.graph_objects as go
from django.conf import settings
from plotly.offline import plot
from wormfunconn import FunctionalAtlas


class WormfunconnToPlot:
    """
    contains a set of methods for calling wormfuconn package to generate parameters plot,
    and url for displaying neural response plot(s) on the webpage
    capture error in each step and then log it to a dictionary (app_error_dict) in output
    """

    @classmethod
    def get_funatlas(cls):
        # Get atlas folder and file name
        folder = os.path.join(settings.MEDIA_ROOT, "atlas/")
        # use mock file for now, need feedback from the lab
        fname = "mock.pickle"
        app_error_dict = {}

        # Create FunctionalAtlas instance from file
        if os.path.isfile(os.path.join(folder, fname)):
            funatlas = FunctionalAtlas.from_file(folder, fname)
        else:
            funatlas = None
            app_error_dict["atlas_file_error"] = "Input Atlas file was not found"
        return funatlas, app_error_dict

    @staticmethod
    def t_max_to_dt(t_max, nt):
        dt = t_max / nt
        return dt

    @staticmethod
    def dt_to_t_max(dt, nt):
        t_max = dt * nt
        return t_max

    @staticmethod
    def resp_labels_to_dict(labels):
        """
        The labels returned from get_responses is np.array
        the label format: resp_neu_ids (rank)
        e.g.
        array(['AIZR (0)', 'DD6 (1)', 'AINL (2)', 'DVB (3)']
        output:
            convert label to a key/value pair in dictionary: {"resp_neu_id"; rank}
        """
        resp_neu_id_rank_dict = {}
        label_list = labels.tolist()
        for item in label_list:
            m = re.match(r"(\w+) (\()(\d+)(\))", item)
            resp_neu_id_rank_dict[m[1]] = int(m[3])
        return resp_neu_id_rank_dict

    @staticmethod
    def get_reqd_params_keys(input_stim_type):
        """
        For a stim_type, get kwargs required by FunctionalAtlas.get_standard_stimulus method
        """
        # shared kwargs for all stim_types
        reqd_params_keys = [
            "stim_type",
            "stim_neu_id",
            "resp_neu_ids",
            "nt",
            "t_max",
            "top_n",
        ]
        # add other keys based on stim_type
        stim_kwargs = FunctionalAtlas.get_standard_stim_kwargs(input_stim_type)
        for i in range(len(stim_kwargs)):
            reqd_params_keys.append(stim_kwargs[i]["name"])
        return reqd_params_keys

    def get_reqd_params_dict(self, params_dict):
        """
        params_dict:
            expect to get from request with POST or GET method
            The form contains parameters for all stim_type, though only display required fields based on stim_type
        output:
            reqd_params_dict: filtered keys/values based on stim_type
            app_error_dict: logged errors
        """
        self.params_dict = params_dict
        # set default values
        reqd_params_dict = {}
        app_error_dict = {}

        # input need to be a dictionary
        if type(params_dict) is dict:
            # verify stim_type
            stim_type = params_dict["stim_type"]
            exp_stim_type_list = ["rectangular", "delta", "sinusoidal", "realistic"]
            if stim_type in exp_stim_type_list:
                reqd_params_keys = self.get_reqd_params_keys(stim_type)
                reqd_params_dict = {key: params_dict[key] for key in reqd_params_keys}
            else:
                app_error_dict[
                    "input_parameter_error"
                ] = f"undefined stim_type:{stim_type}."
        else:
            app_error_dict["input_parameter_error"] = "input is not a dictionary."
        return reqd_params_dict, app_error_dict

    def get_resp_in_ndarray(self, params_dict):
        self.params_dict = params_dict
        reqd_params_dict, app_error_dict = self.get_reqd_params_dict(params_dict)
        # default value
        stim = np.empty(0)
        out_resp_labels_to_dict = {}

        if reqd_params_dict:
            # get required values for every stim_type first
            stim_type = reqd_params_dict["stim_type"]
            nt = int(reqd_params_dict["nt"])
            t_max = float(reqd_params_dict["t_max"])
            dt = self.t_max_to_dt(t_max, nt)
            stim_neu_id = reqd_params_dict["stim_neu_id"]
            resp_neu_ids = reqd_params_dict["resp_neu_ids"]
            if len(resp_neu_ids) == 0:
                resp_neu_ids = None
            top_n = reqd_params_dict["top_n"]
            if top_n is None or top_n == "None":
                top_n = None
            else:
                top_n = int(top_n)

            # Create FunctionalAtlas instance from file
            funatlas, app_error_dict = self.get_funatlas()

            # call get_standard_stimulus based on stim_type
            if funatlas:
                try:
                    if stim_type == "rectangular":
                        duration = float(reqd_params_dict["duration"])
                        stim = funatlas.get_standard_stimulus(
                            nt, dt=dt, stim_type=stim_type, duration=duration
                        )
                    elif stim_type == "delta":
                        stim = funatlas.get_standard_stimulus(
                            nt, dt=dt, stim_type=stim_type, duration=dt
                        )
                    elif stim_type == "sinusoidal":
                        frequency = float(reqd_params_dict["frequency"])
                        phi0 = float(reqd_params_dict["phi0"])
                        stim = funatlas.get_standard_stimulus(
                            nt,
                            dt=dt,
                            stim_type=stim_type,
                            frequency=frequency,
                            phi0=phi0,
                        )
                    elif stim_type == "realistic":
                        tau1 = float(reqd_params_dict["tau1"])
                        tau2 = float(reqd_params_dict["tau2"])
                        stim = funatlas.get_standard_stimulus(
                            nt, dt=dt, stim_type=stim_type, tau1=tau1, tau2=tau2
                        )
                except Exception as e:
                    stim = np.empty(0)
                    app_error_dict["get_standard_stimulus_error"] = e

        # Get responses
        try:
            if stim.size > 0:
                resp, labels, msg = funatlas.get_responses(
                    stim,
                    dt,
                    stim_neu_id,
                    resp_neu_ids=resp_neu_ids,
                    threshold=0.0,
                    top_n=top_n,
                )
            elif stim.size == 0:
                resp = np.empty(0)
                labels = []
                msg = None
        except Exception as e:
            app_error_dict["get_responses_error"] = e
            resp = np.empty(0)
            labels = []
            msg = None

        # if resp_neu_ids is None, the repsonses are for all neurons, need to filter based on top_n ranks
        if resp_neu_ids is None and (type(top_n) is int):
            resp = resp[:top_n]
            labels = labels[:top_n]
            # filtered resp_neu_ids with rank
            out_resp_labels_to_dict = self.resp_labels_to_dict(labels)
            out_resp_neu_ids = out_resp_labels_to_dict.keys()
            # remove the message for stim_neu_id if it is not in filtered response output
            if len(out_resp_neu_ids) > 0 and stim_neu_id not in out_resp_neu_ids:
                msg_str = f"The activity of the stimulated neuron ({stim_neu_id}) is the activity set as stimulus."
                msg = msg.replace(msg_str, "")
            # change message if no response plot
            elif len(out_resp_neu_ids) == 0:
                msg = "Select responsing neuron(s) or set top N >0 to generate neural response plot(s)."
            else:
                msg = msg

        return resp, labels, msg, app_error_dict

    def get_plot_html_div(self, params_dict):
        """
        convert and verify values for plotting neural responses using plotly
        ref: https://plotly.com/python/line-charts/#line-plot-with-goscatter
        ref: https://albertrtk.github.io/2021/01/24/Graph-on-a-web-page-with-Plotly-and-Django.html
        """
        self.params_dict = params_dict

        # get response related output
        resp, labels, msg, app_error_dict = self.get_resp_in_ndarray(params_dict)

        # default value
        plot_div = None
        resp_msg = None
        if msg is not None and msg != "":
            resp_msg = "Notes:\n" + msg

        if resp.size > 0:
            stim_neu_id = params_dict["stim_neu_id"]
            # transposed array for response datasets
            y_data_set = resp.T
            x_data = np.arange(y_data_set.shape[0])

            graphs = []
            for i in range(len(labels)):
                y_data = y_data_set[..., i]
                # adding scatter plot of each set of y_data vs. x_data
                graphs.append(
                    go.Scatter(
                        x=x_data,
                        y=y_data,
                        mode="lines",
                        name=labels[i],
                    )
                )

            # layout of the figure.
            layout = {
                "title": f"Plot: Neural Responses to Stimulated Neuron ({stim_neu_id})",
                "xaxis_title": "Time Point",
                "yaxis_title": "Neural Response",
                "legend_title_text": "Responding Neuron (rank)",
                "showlegend": True,
                "height": 800,
                "width": 1200,
            }

            """
            Getting HTML needed to render the plot
            ref: https://github.com/plotly/plotly.py/blob/master/packages/python/plotly/plotly/offline/offline.py
            Notes:
                plotly.offline.plot function has following arguments set to True as default:
                validate (default=True): validate that all of the keys in the figure are valid
                include_plotlyjs (default=True):
                a script tag containing the plotly.js source code (~3MB) is included in the output.
                plot_div should have passed validations if no error raised
            """
            try:
                plot_div = plot({"data": graphs, "layout": layout}, output_type="div")
            except Exception as e:
                app_error_dict["plot_html_data_error"] = e

        return plot_div, resp_msg, app_error_dict

    def get_url_query_string_for_plot(self, params_dict):
        """
        create url from a dictionary for required parameters
        """
        self.reqd_params_dict = params_dict
        reqd_params_dict, app_error_dict = self.get_reqd_params_dict(params_dict)
        if reqd_params_dict:
            """
            filtered_params_dict = {
                k: v for (k, v) in reqd_params_dict.items() if v is not None
            }
            try:
                url_query_string = urlencode(filtered_params_dict, doseq=True)
            """
            try:
                print("reqd_params_dict:", reqd_params_dict)
                url_query_string = urlencode(reqd_params_dict, doseq=True)
            except Exception as e:
                app_error_dict["plot_url_error"] = e
        else:
            url_query_string = None
        return url_query_string, app_error_dict

    def get_code_snippet_for_plot(self, params_dict):
        """
        call "get_code_snippet" method to get code snippet based on kwargs for a stim_type
        """
        self.params_dict = params_dict
        reqd_params_dict, app_error_dict = self.get_reqd_params_dict(params_dict)
        # get required values for every stim_type first
        stim_type = reqd_params_dict["stim_type"]
        stim_neu_id = reqd_params_dict["stim_neu_id"]
        resp_neu_ids = reqd_params_dict["resp_neu_ids"]
        nt = int(reqd_params_dict["nt"])
        t_max = float(reqd_params_dict["t_max"])

        dt = self.t_max_to_dt(t_max, nt)

        stim_kwargs = {}
        stim_kwargs_list = FunctionalAtlas.get_standard_stim_kwargs(stim_type)
        for i in range(len(stim_kwargs_list)):
            k = stim_kwargs_list[i]["name"]
            stim_kwargs[k] = float(reqd_params_dict[k])

        # get code snippet
        try:
            code_snippet = FunctionalAtlas.get_code_snippet(
                nt, dt, stim_type, stim_kwargs, stim_neu_id, resp_neu_ids
            )
        except Exception as e:
            app_error_dict["plot_code_snippet_error"] = e
        return code_snippet, app_error_dict
