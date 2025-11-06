#include "service_6.h"

Service6::Service6() {}

void Service6::execute() {
    for (auto& cb : callbacks_) cb();
}

void Service6::registerCallback(std::function<void()> cb) {
    callbacks_.push_back(cb);
}
