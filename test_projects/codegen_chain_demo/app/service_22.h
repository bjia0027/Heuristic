#pragma once
#include <functional>
#include <vector>

class Service22 {
public:
    Service22();
    void execute();
    void registerCallback(std::function<void()> cb);
private:
    std::vector<std::function<void()>> callbacks_;
};
